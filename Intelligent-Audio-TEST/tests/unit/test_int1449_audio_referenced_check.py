# -*- coding: utf-8 -*-
"""INT-1449 专项：音频删除 ACL 引用检查改定点查询（替代全表分页 + config 字符串扫描）。

覆盖：
- 仓储 check_audio_referenced：testcases（主音频/干扰人/段级噪声）/ background_noise /
  tasks（task_case_relations 关联用例引用）三路计数
- 定点语义：audio_id=5 不误匹配 audio_id=50（JSON 数字值字符类收尾）
- 可见性/软删口径：软删用例不计、软删任务不计、shared 可见
- 全链：TaskConfigService.CheckAudioReferenced servicer → query handler → 查询服务 → 仓储

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)

_TABLES = None


def _ensure_db():
    init_db(pool_size=2)


def _ensure_tables():
    """创建引用检查链涉及的表（TestCase/Task/TaskCase/Tag...）。"""
    _ensure_db()
    global _TABLES
    if _TABLES is None:
        from task_service.infrastructure.persistence.models import (
            Task, TaskCase, TestCase,
        )
        _TABLES = [t.__table__ for t in (Task, TaskCase, TestCase)]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


def _cleanup():
    from sqlalchemy import text

    session = get_db_session()
    try:
        session.execute(text('DELETE FROM task_case_relations'))
        session.execute(text('DELETE FROM test_tasks'))
        session.execute(text('DELETE FROM test_cases'))
        session.commit()
    finally:
        remove_db_session()


def _seed_cases(rows):
    """插入用例行。rows: [(id, name, config_dict, deleted, visibility, owner), ...]"""
    from task_service.infrastructure.persistence.models import TestCase

    session = get_db_session()
    try:
        for row in rows:
            cid, name, config = row[0], row[1], row[2]
            deleted = row[3] if len(row) > 3 else False
            visibility = row[4] if len(row) > 4 else 'shared'
            owner = row[5] if len(row) > 5 else None
            session.add(TestCase(
                id=cid, name=name, config=config,
                deleted=deleted, visibility=visibility, created_by_user_id=owner,
            ))
        session.commit()
    finally:
        remove_db_session()


def _seed_tasks(rows):
    """插入任务行。rows: [(id, name, deleted, visibility, owner), ...]"""
    from task_service.infrastructure.persistence.models import Task

    session = get_db_session()
    try:
        for row in rows:
            tid, name = row[0], row[1]
            deleted = row[2] if len(row) > 2 else False
            visibility = row[3] if len(row) > 3 else 'shared'
            owner = row[4] if len(row) > 4 else None
            session.add(Task(
                id=tid, name=name, deleted=deleted,
                visibility=visibility, created_by_user_id=owner,
            ))
        session.commit()
    finally:
        remove_db_session()


def _seed_task_cases(rows):
    """插入任务-用例关联行。rows: [(task_id, test_case_id), ...]"""
    from task_service.infrastructure.persistence.models import TaskCase

    session = get_db_session()
    try:
        for task_id, test_case_id in rows:
            session.add(TaskCase(task_id=task_id, test_case_id=test_case_id))
        session.commit()
    finally:
        remove_db_session()


class TestCheckAudioReferencedRepository:
    """仓储层 check_audio_referenced 三路计数与定点语义。"""

    def setup_method(self):
        _ensure_tables()
        _cleanup()

    def _counts(self, audio_id, user_id=None):
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        return testcase_repository.check_audio_referenced(audio_id, user_id=user_id)

    def test_main_audio_in_rounds(self):
        _seed_cases([
            ('C1', '主音频引用', {'rounds': [{'audios': [{'audio_id': 5, 'spl': 60}]}]}),
            ('C2', '无引用', {'rounds': [{'audios': [{'audio_id': 99, 'spl': 60}]}]}),
        ])
        counts = self._counts(5)
        assert counts['testcases'] == 1
        assert counts['background_noise'] == 0
        assert counts['tasks'] == 0

    def test_noise_case_level(self):
        _seed_cases([
            ('C1', '背景噪声', {
                'rounds': [{'audios': [{'audio_id': 9}]}],
                'background_noise': {'audio_id': 5, 'spl': 60.0, 'loop': True},
            }),
        ])
        counts = self._counts(5)
        # 旧口径：主音频检查命中任意 audio_id，噪声检查命中 background_noise 块
        assert counts['testcases'] == 1
        assert counts['background_noise'] == 1

    def test_noise_round_level(self):
        _seed_cases([
            ('C1', '轮次背景噪声', {
                'rounds': [{'audios': [{'audio_id': 9}], 'background_noise': {'audio_id': 5}}],
            }),
        ])
        counts = self._counts(5)
        assert counts['background_noise'] == 1

    def test_interferer_counts_as_testcase(self):
        """干扰人 audio_id 也被主音频检查覆盖（旧字符串匹配同口径）。"""
        _seed_cases([
            ('C1', '干扰人', {
                'rounds': [{'audios': [{'audio_id': 9, 'interferers': [{'audio_id': 5}]}]}],
            }),
        ])
        counts = self._counts(5)
        assert counts['testcases'] == 1
        assert counts['background_noise'] == 0

    def test_no_false_positive_for_prefix_id(self):
        """定点语义：audio_id=5 不命中只引用 audio_id=50 的用例（字符类收尾）。"""
        _seed_cases([
            ('C50', '只引用50', {'rounds': [{'audios': [{'audio_id': 50, 'spl': 60}]}]}),
            ('C500', '只引用500', {'rounds': [{'audios': [{'audio_id': 500, 'spl': 60}]}]}),
        ])
        assert self._counts(5)['testcases'] == 0
        assert self._counts(50)['testcases'] == 1
        assert self._counts(500)['testcases'] == 1

    def test_deleted_case_not_counted(self):
        _seed_cases([
            ('C1', '软删引用', {'rounds': [{'audios': [{'audio_id': 5}]}]}, True),
            ('C2', '活跃引用', {'rounds': [{'audios': [{'audio_id': 5}]}]}, False),
        ])
        assert self._counts(5)['testcases'] == 1

    def test_private_invisible_case_not_counted_anonymously(self):
        """未认证（无 user_id）仅 shared 可见：private 引用不计数（对齐 ListTestCases 口径）。"""
        _seed_cases([
            ('C1', '私有引用', {'rounds': [{'audios': [{'audio_id': 5}]}]}, False, 'private', 101),
            ('C2', '共享引用', {'rounds': [{'audios': [{'audio_id': 5}]}]}, False, 'shared', None),
        ])
        assert self._counts(5)['testcases'] == 1
        assert self._counts(5, user_id=101)['testcases'] == 2

    def test_tasks_via_case_relations(self):
        _seed_cases([
            ('C1', '被引用', {'rounds': [{'audios': [{'audio_id': 5}]}]}),
            ('C2', '未被引用', {'rounds': [{'audios': [{'audio_id': 99}]}]}),
        ])
        _seed_tasks([
            (1, '任务A', False),
            (2, '任务B', False),
            (3, '任务C软删', True),
        ])
        _seed_task_cases([
            (1, 'C1'),
            (2, 'C2'),
            (3, 'C1'),  # 软删任务关联引用音频 → 不计
        ])
        counts = self._counts(5)
        assert counts['testcases'] == 1
        assert counts['tasks'] == 1  # 仅任务A

    def test_no_audio_id_returns_zeros(self):
        assert self._counts(None) == {'testcases': 0, 'background_noise': 0, 'tasks': 0}
        assert self._counts(0) == {'testcases': 0, 'background_noise': 0, 'tasks': 0}


class TestCheckAudioReferencedServicerChain:
    """servicer → query handler → 查询服务 → 仓储 全链。"""

    def setup_method(self):
        _ensure_tables()
        _cleanup()

    def _call_servicer(self, audio_id):
        from shared.proto import task_service_pb2 as task_pb
        from task_service.interfaces.grpc.task_config import TaskConfigServiceServicer
        servicer = TaskConfigServiceServicer()
        resp = servicer.CheckAudioReferenced(
            task_pb.CheckAudioReferencedRequest(audio_id=audio_id), context=None)
        from shared.utils.grpc_json import loads as _loads
        assert resp.success
        return _loads(resp.data, {})

    def test_servicer_returns_counts(self):
        _seed_cases([
            ('C1', '被引用', {'rounds': [{'audios': [{'audio_id': 7}]}]}),
            ('C2', '噪声', {'background_noise': {'audio_id': 7}}),
        ])
        data = self._call_servicer(7)
        assert data['testcases'] == 2
        assert data['background_noise'] == 1

    def test_servicer_missing_audio_is_zero(self):
        _seed_cases([
            ('C1', '无引用', {'rounds': [{'audios': [{'audio_id': 9}]}]}),
        ])
        data = self._call_servicer(7)
        assert data == {'testcases': 0, 'background_noise': 0, 'tasks': 0}

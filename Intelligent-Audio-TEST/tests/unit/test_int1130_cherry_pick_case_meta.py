# -*- coding: utf-8 -*-
"""INT-1130 专项：挑选合并候选行补用例卡元信息（tags/分组/时长/轮次，§11-7）。

覆盖（对齐卡验收①）：
- 候选行在 case_id/case_name/algorithm_type 基础上补 tags/group_id/group_name/
  duration/rounds；
- 真实分组/标签用例正确返回对应值（去重保序）；
- duration 同源用例管理列表 total_duration 口径（collect_audios 逐音频时长累加，
  经 audio_service gRPC 批量查询），无音频/无时长返回 None；
- rounds 返回 len(config.get('rounds') or [])（轮次数，非数组本身）；
- 无分组/标签/轮次用例返回缺省 []/null/0。

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all，用例内自行清理，
对齐 test_int577 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///./TEMP/int1130_proc.db')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from shared.infrastructure.user_context import set_current_user_id

_TASK_TABLES = None


def _ensure_tables():
    global _TASK_TABLES
    if _TASK_TABLES is None:
        init_db(pool_size=2)
        from task_service.infrastructure.persistence.models import (
            Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI, Favorite,
            Tag, TaskTag, TestCase, TestCaseGroup, TestCaseTag, TestResult,
            CherryPickCartItem, TaskCherryPickRelation, CherryPickSet, CherryPickSetItem,
        )
        _TASK_TABLES = [t.__table__ for t in (
            Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI, Favorite,
            Tag, TaskTag, TestCase, TestCaseGroup, TestCaseTag, TestResult,
            CherryPickCartItem, TaskCherryPickRelation, CherryPickSet, CherryPickSetItem,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TASK_TABLES)
    return _TASK_TABLES


def _cleanup(tables):
    session = get_db_session()
    try:
        for table in tables:
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


@pytest.fixture()
def db():
    tables = _ensure_tables()
    _cleanup(tables)
    yield tables
    _cleanup(tables)


def _seed_source_task(name='INT1130源任务', status='completed',
                      algorithm_type='asr'):
    """种子：终态源任务 + 2 用例 2 结果。

    用例 C1：带分组（g1）+ 3 标签（含 1 同名，验证去重）+ 2 轮配置（音频 1001/1002）；
    用例 C2：无分组/无标签/空配置（缺省兜底）。
    返回 (task_id, [(case_id, result_id, device_id)...])
    """
    from task_service.infrastructure.persistence.models import (
        Task, TestCase, TestCaseGroup, Tag, TestResult,
    )
    session = get_db_session()
    try:
        group = TestCaseGroup(id='g1', name='INT1130分组A')
        session.add(group)
        tag_a = Tag(name='INT1130标签1')
        tag_b = Tag(name='INT1130标签2')
        tag_a_dup = Tag(name='INT1130标签1')  # 同名去重验证
        session.add_all([tag_a, tag_b, tag_a_dup])
        session.flush()

        task = Task(name=name, status=status, total_cases=2,
                    algorithm_type=algorithm_type)
        session.add(task)
        session.flush()

        if session.query(TestCase).filter(TestCase.id == 'INT1130-C1').first() is None:
            tc1 = TestCase(
                id='INT1130-C1',
                name='带分组标签用例（INT1130）',
                description='',
                group_id='g1',
                config={
                    'rounds': [
                        {'roundNumber': 1, 'audios': [{'audio_id': 1001, 'play_order': 1}]},
                        {'roundNumber': 2, 'audios': [{'audio_id': 1002, 'play_order': 1}]},
                    ],
                },
                algorithm_type=algorithm_type,
            )
            tc1.tags = [tag_a, tag_b, tag_a_dup]
            session.add(tc1)
        if session.query(TestCase).filter(TestCase.id == 'INT1130-C2').first() is None:
            session.add(TestCase(
                id='INT1130-C2',
                name='无分组标签用例（INT1130）',
                description='',
                config={},
                algorithm_type=algorithm_type,
            ))

        results = []
        for i, case_id in enumerate(['INT1130-C1', 'INT1130-C2']):
            r = TestResult(
                task_id=task.id, test_case_id=case_id, device_id=7 + i,
                algorithm_type=algorithm_type, execution_status='completed',
                algorithm_result={'asr_result': f'文本{i}'},
            )
            session.add(r)
            session.flush()
            results.append((case_id, r.id, r.device_id))
        session.commit()
        return task.id, results
    finally:
        remove_db_session()


def test_candidates_case_meta(db, monkeypatch):
    """§11-7：候选行补 tags/group_id/group_name/duration/rounds（含去重与缺省兜底）。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    # duration 同源 total_duration：音频时长批量查询（mock 时长；INT-1625 起为
    # ACL 共享库窄字段投影 get_audio_durations）
    from task_service.infrastructure.acl import audio_acl_repository as audio_acl_mod
    monkeypatch.setattr(
        audio_acl_mod.audio_acl_repository, 'get_audio_durations',
        lambda audio_ids, session=None: {1001: 10.5, 1002: 5.25})

    _task_id, _results = _seed_source_task()
    resp = cherry_pick_service.list_candidates({'task_ids': [_task_id], 'page': 1, 'per_page': 50})
    assert resp['success'] is True
    items = resp['data']['items']
    assert len(items) == 2
    by_case = {it['case_id']: it for it in items}

    c1 = by_case['INT1130-C1']
    # 分组/标签：真实值返回（标签去重保序）
    assert c1['tags'] == ['INT1130标签1', 'INT1130标签2']
    assert c1['group_id'] == 'g1'
    assert c1['group_name'] == 'INT1130分组A'
    # 时长：collect_audios 逐音频累加（10.5 + 5.25 = 15.75）
    assert c1['duration'] == 15.75
    # 轮次：config.rounds 轮次数（2 轮）
    assert c1['rounds'] == 2

    c2 = by_case['INT1130-C2']
    # 无分组/标签/轮次：缺省兜底（[]/null/0）
    assert c2['tags'] == []
    assert c2['group_id'] is None
    assert c2['group_name'] is None
    assert c2['duration'] is None
    assert c2['rounds'] == 0

    # 既有字段不回归（§11-2）
    assert c1['case_name'] == '带分组标签用例（INT1130）'
    assert c1['algorithm_type'] == 'asr'


def test_candidates_case_meta_container_hit(db, monkeypatch):
    """INT-657 容器任务命中行同补用例元信息（候选行按 result.test_case_id 取元信息）。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    from task_service.infrastructure.persistence.models import Task, TestCase, TestCaseGroup, Tag, TestResult

    from task_service.infrastructure.acl import audio_acl_repository as audio_acl_mod
    monkeypatch.setattr(
        audio_acl_mod.audio_acl_repository, 'get_audio_durations',
        lambda audio_ids, session=None: {2001: 8.0})

    session = get_db_session()
    try:
        session.add(TestCaseGroup(id='g2', name='INT1130容器分组'))
        session.flush()
        tc = TestCase(id='INT1130-CT', name='容器命中用例', description='', group_id='g2',
                      config={'rounds': [{'roundNumber': 1, 'audios': [{'audio_id': 2001}]}]})
        tag = Tag(name='INT1130容器标签')
        session.add(tag)
        session.flush()
        tc.tags = [tag]
        session.add(tc)

        src = Task(name='INT1130容器源', status='completed', total_cases=1,
                   algorithm_type='asr')
        session.add(src)
        session.flush()
        r = TestResult(task_id=src.id, test_case_id='INT1130-CT', device_id=11,
                       algorithm_type='asr', execution_status='completed',
                       algorithm_result={'a': 1})
        session.add(r)
        session.flush()
        # 容器任务：经 checkout_merge 下单（含引用关系）
        set_current_user_id(42)
        from task_service.application.task.cherry_pick_service import cherry_pick_service as cp
        cp.cart_add({'result_ids': [r.id]})
        checkout = cp.checkout_merge({'name': 'INT1130容器'})
        assert checkout['success'] is True
        container_id = checkout['data']['task_id']
        session.commit()
    finally:
        remove_db_session()

    resp = cherry_pick_service.list_candidates({'task_ids': [container_id], 'page': 1, 'per_page': 50})
    assert resp['success'] is True
    items = resp['data']['items']
    assert len(items) == 1
    item = items[0]
    assert item['task_id'] == container_id
    assert item['case_id'] == 'INT1130-CT'
    assert item['tags'] == ['INT1130容器标签']
    assert item['group_id'] == 'g2'
    assert item['group_name'] == 'INT1130容器分组'
    assert item['duration'] == 8.0
    assert item['rounds'] == 1

# -*- coding: utf-8 -*-
"""INT-1625 专项：挑选候选聚合的按行放大慢路径（per_page=200 超时）。

覆盖（对齐卡验收「后端 gRPC 聚合消除按行放大的慢路径」）：
- 候选行 `evaluated` 标记与 `evaluation_status` 筛选改走存在性投影
  `get_evaluated_result_ids`，不再经 `GetDimensionResultsByResultIds` 回传
  全部维度行（真实库首页 200 个结果 ID = 5592 行，宿主实测 5~22s）；
- 候选行 `result_type` 改 DB-first（INT-1510 §8.2.3 收口）：直接取落库列，
  请求路径零 OSS 往返（INT-1625 的并发文件预取已删除，本文件两条用例随口径改写）；
- 用例时长取窄字段 `get_audio_durations`（原 `GetAudiosByIds` 逐音频 N+1）。

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all，用例内自行清理，
对齐 test_int1130 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///./TEMP/int1625_proc.db')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)

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


def _seed(rows):
    """种子：1 个终态源任务 + 按 rows 建结果。

    rows: [(case_id, result_data, result_data_path, result_type)...]
    返回 (task_id, [result_id...])
    """
    from task_service.infrastructure.persistence.models import Task, TestCase, TestResult
    session = get_db_session()
    try:
        task = Task(name='INT1625源任务', status='completed', total_cases=len(rows),
                    algorithm_type='asr')
        session.add(task)
        session.flush()
        result_ids = []
        for idx, row in enumerate(rows):
            case_id, result_data, path = row[0], row[1], row[2]
            result_type = row[3] if len(row) > 3 else None
            if session.query(TestCase).filter(TestCase.id == case_id).first() is None:
                session.add(TestCase(id=case_id, name=f'INT1625用例{idx}',
                                     description='', config={}, algorithm_type='asr'))
            r = TestResult(task_id=task.id, test_case_id=case_id, device_id=7,
                           algorithm_type='asr', execution_status='completed',
                           algorithm_result={'idx': idx}, result_data=result_data,
                           result_data_path=path, result_type=result_type)
            session.add(r)
            session.flush()
            result_ids.append(r.id)
        session.commit()
        return task.id, result_ids
    finally:
        remove_db_session()


def test_candidates_evaluated_uses_existence_projection(db, monkeypatch):
    """evaluated 标记走存在性投影，不再拉全部维度行。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    from task_service.infrastructure.acl import evaluation_config_acl_repository as eval_acl_mod

    task_id, result_ids = _seed([
        ('INT1625-C1', {'a': 1}, None),
        ('INT1625-C2', {'a': 2}, None),
    ])

    calls = {}

    def _fake_evaluated(ids, session=None):
        calls['ids'] = sorted(ids)
        return {result_ids[0]}

    def _forbidden(_ids):
        raise AssertionError('不该再走 GetDimensionResultsByResultIds 全量维度行 RPC')

    monkeypatch.setattr(eval_acl_mod.evaluation_config_acl_repository,
                        'get_evaluated_result_ids', _fake_evaluated)
    monkeypatch.setattr(eval_acl_mod.evaluation_config_acl_repository,
                        'get_dimension_results_by_result_ids', _forbidden)

    resp = cherry_pick_service.list_candidates({'task_ids': [task_id], 'page': 1, 'per_page': 50})
    assert resp['success'] is True
    items = {it['result_id']: it for it in resp['data']['items']}
    assert items[result_ids[0]]['evaluated'] is True
    assert items[result_ids[1]]['evaluated'] is False
    # 存在性投影只按本页结果 ID 批量取一次
    assert calls['ids'] == sorted(result_ids)


def test_candidates_evaluation_status_filter_uses_existence_projection(db, monkeypatch):
    """evaluation_status 筛选同样不再按范围拉全部维度行（原先可放大到全库）。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    from task_service.infrastructure.acl import evaluation_config_acl_repository as eval_acl_mod

    task_id, result_ids = _seed([
        ('INT1625-C3', {'a': 3}, None),
        ('INT1625-C4', {'a': 4}, None),
    ])
    monkeypatch.setattr(eval_acl_mod.evaluation_config_acl_repository,
                        'get_evaluated_result_ids',
                        lambda ids, session=None: {result_ids[0]})
    monkeypatch.setattr(eval_acl_mod.evaluation_config_acl_repository,
                        'get_dimension_results_by_result_ids',
                        lambda _ids: (_ for _ in ()).throw(AssertionError('不该走全量 RPC')))

    resp = cherry_pick_service.list_candidates({
        'task_ids': [task_id], 'evaluation_status': 'completed', 'page': 1, 'per_page': 50})
    assert resp['success'] is True
    assert [it['result_id'] for it in resp['data']['items']] == [result_ids[0]]


def test_result_type_from_db_column_without_oss(db, monkeypatch):
    """result_type 取落库列（INT-1510 DB-first）：带文件路径也不再回源 OSS。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    from shared.infrastructure.storage import storage
    from shared.utils import result_data_store as rds

    task_id, result_ids = _seed([
        ('INT1625-C5', None, 'case_result/1/a/result_data.json', 'asr'),
        ('INT1625-C6', {'result_type': 'api'}, 'case_result/1/b/result_data.json', 'voice'),
        # 缺值落库 NULL → 对外 default（待补充桶），同样不读文件
        ('INT1625-C7', None, 'case_result/1/c/result_data.json', None),
    ])

    def _boom(*_args, **_kwargs):
        raise AssertionError('候选查询不得回源对象存储（INT-1510 §8.2.3）')

    monkeypatch.setattr(storage, 'exists', _boom)
    monkeypatch.setattr(storage, 'load_bytes', _boom)
    monkeypatch.setattr(rds, 'read_result_data_file', _boom)

    resp = cherry_pick_service.list_candidates({'task_ids': [task_id], 'page': 1, 'per_page': 50})
    assert resp['success'] is True
    by_result = {it['result_id']: it for it in resp['data']['items']}
    assert by_result[result_ids[0]]['result_type'] == 'asr'
    assert by_result[result_ids[1]]['result_type'] == 'voice'
    assert by_result[result_ids[2]]['result_type'] == 'default'


def test_result_type_missing_column_falls_back_to_default(db, monkeypatch):
    """落库缺值（NULL）统一输出 default，不报错。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    from shared.utils import result_data_store as rds

    task_id, result_ids = _seed([
        ('INT1625-C8', {'result_type': 'voice'}, 'case_result/1/c/result_data.json', None),
    ])

    def _boom(*_args, **_kwargs):
        raise AssertionError('缺值行不得回源对象存储')

    monkeypatch.setattr(rds, 'read_result_data_file', _boom)

    resp = cherry_pick_service.list_candidates({'task_ids': [task_id], 'page': 1, 'per_page': 50})
    assert resp['success'] is True
    # 读侧只看落库列：行内 JSON 的 voice 不再在请求路径解析
    assert resp['data']['items'][0]['result_type'] == 'default'


def test_audio_durations_uses_narrow_projection(db, monkeypatch):
    """用例时长走窄字段投影 get_audio_durations（不再 GetAudiosByIds 逐音频 N+1）。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    from task_service.infrastructure.acl import audio_acl_repository as audio_acl_mod
    from task_service.infrastructure.persistence.models import TestCase
    from shared.models.database import get_db_session as _s

    task_id, _ = _seed([('INT1625-C9', {'a': 9}, None)])
    session = _s()
    try:
        session.query(TestCase).filter(TestCase.id == 'INT1625-C9').update({
            'config': {'rounds': [
                {'roundNumber': 1, 'audios': [{'audio_id': 3001}, {'audio_id': 3002}]},
            ]},
        })
        session.commit()
    finally:
        remove_db_session()

    monkeypatch.setattr(audio_acl_mod.audio_acl_repository, 'get_audio_durations',
                        lambda audio_ids, session=None: {3001: 1.5, 3002: 2.25})
    monkeypatch.setattr(audio_acl_mod.audio_acl_repository, 'list_audios_by_ids',
                        lambda _ids: (_ for _ in ()).throw(AssertionError('不该走 GetAudiosByIds')))

    resp = cherry_pick_service.list_candidates({'task_ids': [task_id], 'page': 1, 'per_page': 50})
    assert resp['success'] is True
    assert resp['data']['items'][0]['duration'] == 3.75

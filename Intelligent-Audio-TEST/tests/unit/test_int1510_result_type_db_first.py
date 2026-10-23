# -*- coding: utf-8 -*-
"""INT-1510 专项：candidates 行接口 result_type 落库 + DB-first（零 OSS）+ 服务端过滤。

覆盖（卡验收 1，设计文档 §8.2.3 第 1/4 条、§8.2.4「candidates 增量参数」）：
- 候选行 `result_type` 取自 DB 落库列，请求路径零对象存储往返：把
  `storage.exists` / `storage.load_bytes` / `read_result_data_file` 全部
  monkeypatch 成抛错，带 `result_data_path` 的候选行仍正常返回；
- `api_ids` / `result_type` 服务端过滤（`default` 命中缺值桶），条件组合 AND；
- 过滤后分页 `total` = 命中数、逐页 result_id 不重不漏；
- `select_all` 返回集合 = 同条件全量 result_id 集合；
- 写路径 `submit()` 物化 result_type（显式值优先、否则读 DB 轻量 JSON、
  缺值落 NULL）。

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all，用例内自行清理，
对齐 test_int1625 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///./TEMP/int1510_proc.db')

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
    """种子：1 个终态源任务 + 按 rows 建结果行。

    rows: [{'case_id': str, 'api_id': int|None, 'device_id': int|None,
            'result_type': str|None, 'result_data': dict|None,
            'result_data_path': str|None}]，返回 (task_id, [result_id...])。
    """
    from task_service.infrastructure.persistence.models import Task, TestCase, TestResult
    session = get_db_session()
    try:
        task = Task(name='INT1510源任务', status='completed', total_cases=len(rows),
                    algorithm_type='asr')
        session.add(task)
        session.flush()
        result_ids = []
        for idx, row in enumerate(rows):
            case_id = row['case_id']
            if session.query(TestCase).filter(TestCase.id == case_id).first() is None:
                session.add(TestCase(id=case_id, name=f'INT1510用例{idx}',
                                     description='', config={}, algorithm_type='asr'))
            r = TestResult(task_id=task.id, test_case_id=case_id,
                           device_id=row.get('device_id', 7),
                           api_id=row.get('api_id'),
                           algorithm_type='asr', execution_status='completed',
                           algorithm_result={'idx': idx},
                           result_data=row.get('result_data'),
                           result_data_path=row.get('result_data_path'),
                           result_type=row.get('result_type'))
            session.add(r)
            session.flush()
            result_ids.append(r.id)
        session.commit()
        return task.id, result_ids
    finally:
        remove_db_session()


def _forbid_oss(monkeypatch):
    """把对象存储入口全部封死：任何一处在请求路径被调用即失败。"""
    from shared.infrastructure.storage import storage
    from shared.utils import result_data_store as rds

    calls = {'n': 0}

    def _boom(*_args, **_kwargs):
        calls['n'] += 1
        raise AssertionError('候选查询请求路径禁止回源对象存储（§8.2.3 第 1 条）')

    monkeypatch.setattr(storage, 'exists', _boom)
    monkeypatch.setattr(storage, 'load_bytes', _boom)
    monkeypatch.setattr(storage, 'load_file', _boom)
    monkeypatch.setattr(rds, 'read_result_data_file', _boom)
    return calls


def _items(resp):
    return {it['result_id']: it for it in resp['data']['items']}


# ==================== 1. DB-first：零 OSS 往返 ====================

def test_result_type_from_db_column_without_oss(db, monkeypatch):
    """带 result_data_path 的候选行也直接从落库列取值，零 OSS 调用。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    calls = _forbid_oss(monkeypatch)
    task_id, result_ids = _seed([
        # 有文件路径，但 result_type 已在落库列：不得再读文件
        {'case_id': 'INT1510-C1', 'result_type': 'asr',
         'result_data_path': 'case_result/1/a/result_data.json'},
        {'case_id': 'INT1510-C2', 'result_type': 'voice',
         'result_data': {'result_type': 'asr'},
         'result_data_path': 'case_result/1/b/result_data.json'},
        # 缺值落库 NULL → 对外输出 default（结果类型待补充桶）
        {'case_id': 'INT1510-C3', 'result_type': None,
         'result_data_path': 'case_result/1/c/result_data.json'},
    ])

    resp = cherry_pick_service.list_candidates(
        {'task_ids': [task_id], 'page': 1, 'per_page': 50})
    assert resp['success'] is True
    by_result = _items(resp)
    assert by_result[result_ids[0]]['result_type'] == 'asr'
    # 落库列优先，不再按文件/行内 JSON 重新解析
    assert by_result[result_ids[1]]['result_type'] == 'voice'
    assert by_result[result_ids[2]]['result_type'] == 'default'
    assert calls['n'] == 0, '候选查询不得触达对象存储'


def test_result_type_filter_does_not_trigger_oss(db, monkeypatch):
    """result_type 过滤（含 default 桶）同样零 OSS。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    calls = _forbid_oss(monkeypatch)
    task_id, result_ids = _seed([
        {'case_id': 'INT1510-C4', 'result_type': 'asr',
         'result_data_path': 'case_result/1/d/result_data.json'},
        {'case_id': 'INT1510-C5', 'result_type': None,
         'result_data_path': 'case_result/1/e/result_data.json'},
    ])
    resp = cherry_pick_service.list_candidates(
        {'task_ids': [task_id], 'result_type': 'default', 'page': 1, 'per_page': 50})
    assert resp['success'] is True
    assert [it['result_id'] for it in resp['data']['items']] == [result_ids[1]]
    assert calls['n'] == 0


# ==================== 2. 服务端过滤（api_ids / result_type）====================

def test_filters_api_ids_and_result_type_and_combination(db, monkeypatch):
    """api_ids / result_type 各自命中与 AND 组合。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    _forbid_oss(monkeypatch)
    task_id, ids = _seed([
        {'case_id': 'INT1510-F1', 'api_id': 11, 'result_type': 'asr'},
        {'case_id': 'INT1510-F2', 'api_id': 11, 'result_type': 'api'},
        {'case_id': 'INT1510-F3', 'api_id': 22, 'result_type': None},
        {'case_id': 'INT1510-F4', 'api_id': 22, 'result_type': 'asr'},
        {'case_id': 'INT1510-F5', 'api_id': None, 'result_type': 'asr', 'device_id': 9},
    ])

    def _ids(**params):
        resp = cherry_pick_service.list_candidates(
            dict({'task_ids': [task_id], 'page': 1, 'per_page': 50}, **params))
        assert resp['success'] is True
        return [it['result_id'] for it in resp['data']['items']]

    assert sorted(_ids(api_ids=[11])) == sorted([ids[0], ids[1]])
    assert _ids(result_type='default') == [ids[2]]
    assert sorted(_ids(result_type='asr')) == sorted([ids[0], ids[3], ids[4]])
    # AND 组合：api 11 且类型 asr
    assert _ids(api_ids=[11], result_type='asr') == [ids[0]]
    # 与既有设备维度同口径 AND
    assert _ids(api_ids=[11], device_ids=[7]) == sorted([ids[0], ids[1]])
    assert _ids(api_ids=[11], device_ids=[8]) == []


# ==================== 3. 分页 total 与 select_all 同口径 ====================

def test_filtered_pagination_total_and_no_dup_or_miss(db, monkeypatch):
    """过滤后 total = 命中数；逐页 result_id 不重不漏。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    _forbid_oss(monkeypatch)
    rows = []
    for i in range(7):
        rows.append({'case_id': f'INT1510-P{i}', 'api_id': 11,
                     'result_type': 'asr' if i % 2 == 0 else 'api'})
    for i in range(3):
        rows.append({'case_id': f'INT1510-Q{i}', 'api_id': 22, 'result_type': None})
    task_id, ids = _seed(rows)
    expected = set(ids[:7])

    collected = []
    page = 1
    while True:
        resp = cherry_pick_service.list_candidates({
            'task_ids': [task_id], 'api_ids': [11],
            'page': page, 'per_page': 3})
        assert resp['success'] is True
        data = resp['data']
        assert data['total'] == 7
        page_ids = [it['result_id'] for it in data['items']]
        if not page_ids:
            break
        collected += page_ids
        page += 1
    assert len(collected) == 7
    assert set(collected) == expected
    assert len(collected) == len(set(collected)), '逐页 result_id 不得重复'

    # select_all 与列表同口径（含新增过滤参数）
    all_resp = cherry_pick_service.list_candidates({
        'task_ids': [task_id], 'api_ids': [11], 'select_all': True})
    assert all_resp['success'] is True
    assert set(all_resp['data']['result_ids']) == expected

    default_resp = cherry_pick_service.list_candidates({
        'task_ids': [task_id], 'result_type': 'default', 'select_all': True})
    assert set(default_resp['data']['result_ids']) == set(ids[7:])


# ==================== 4. 写路径物化 result_type ====================

def test_submit_materializes_result_type(db, monkeypatch):
    """submit()：显式值优先；否则只读 DB 轻量 JSON；缺值落 NULL（不回源 OSS）。"""
    from task_service.infrastructure.persistence.test_result_repository import (
        TestResultRepository,
    )
    from task_service.infrastructure.persistence.models import TestResult

    _forbid_oss(monkeypatch)
    repo = TestResultRepository()
    task_id, _ = _seed([{'case_id': 'INT1510-W0'}])

    rid_explicit = repo.submit(task_id, {
        'test_case_id': 'INT1510-W1', 'device_id': 7,
        'result_type': 'voice', 'result_data': {'result_type': 'asr'},
    })
    rid_from_json = repo.submit(task_id, {
        'test_case_id': 'INT1510-W2', 'device_id': 7,
        'result_data': {'result_type': 'api'},
    })
    rid_missing = repo.submit(task_id, {
        'test_case_id': 'INT1510-W3', 'device_id': 7,
        'result_data': {'foo': 1},
        'result_data_path': 'case_result/1/w3/result_data.json',
    })

    session = get_db_session()
    try:
        by_id = {r.id: r for r in session.query(TestResult).filter(
            TestResult.id.in_([rid_explicit, rid_from_json, rid_missing])).all()}
    finally:
        remove_db_session()

    assert by_id[rid_explicit].result_type == 'voice'
    assert by_id[rid_from_json].result_type == 'api'
    # 缺值：落库 NULL（对外 default），不回源对象存储
    assert by_id[rid_missing].result_type is None


def test_submit_pending_sentinel_stored_as_null(db):
    """extract_result_type 的缺值哨兵 'default' 不进库（落 NULL = 待补充桶）。"""
    from task_service.infrastructure.persistence.test_result_repository import (
        TestResultRepository,
    )
    from task_service.infrastructure.persistence.models import TestResult

    repo = TestResultRepository()
    task_id, _ = _seed([{'case_id': 'INT1510-W9'}])
    rid = repo.submit(task_id, {
        'test_case_id': 'INT1510-W9', 'device_id': 7, 'result_data': None,
    })
    session = get_db_session()
    try:
        assert session.get(TestResult, rid).result_type is None
    finally:
        remove_db_session()


# ==================== 5. 网关层参数校验与透传 ====================

class _FakeState:
    def __init__(self, json_body=None):
        self._json_body = json_body


class _FakeRequest:
    def __init__(self, query_params=None, json_body=None):
        self.query_params = query_params or {}
        self.state = _FakeState(json_body)


class _FakeAcl:
    def __init__(self):
        self.calls = []

    def list_candidates(self, query):
        self.calls.append(query)
        from api_gateway.domain.dto import CommandResultDTO
        return CommandResultDTO(success=True, data={
            'items': [], 'total': 0, 'page': query.get('page'),
            'per_page': query.get('per_page')})


@pytest.fixture()
def gateway(monkeypatch):
    """替换网关 ACL，捕获透传参数。"""
    from api_gateway.infrastructure import request_adapter
    from api_gateway.application.services.task import cherry_pick_service as svc_mod

    fake = _FakeAcl()
    monkeypatch.setattr(svc_mod, '_cherry_pick_acl', fake)
    request_adapter.set_current_request(_FakeRequest())
    yield fake, request_adapter
    request_adapter.set_current_request(None)


def test_gateway_candidates_defaults_without_new_params(gateway):
    """新增参数缺省不改变既有透传口径。"""
    fake, _ = gateway
    from api_gateway.application.services.task.cherry_pick_service import CherryPickService
    body, code = CherryPickService.list_candidates()
    assert code == 200 and body.get('success') is True
    payload = fake.calls[0]
    assert payload['api_ids'] == []
    assert payload['result_type'] is None


def test_gateway_candidates_passes_api_ids_and_result_type(gateway):
    """api_ids 逗号串拆分为 int 列表；result_type 原样透传。"""
    fake, adapter = gateway
    adapter.set_current_request(_FakeRequest({
        'task_ids': '419,418', 'api_ids': '7,8', 'result_type': 'default',
        'page': '2', 'per_page': '200',
    }))
    from api_gateway.application.services.task.cherry_pick_service import CherryPickService
    body, code = CherryPickService.list_candidates()
    assert code == 200
    payload = fake.calls[0]
    assert payload['api_ids'] == [7, 8]
    assert payload['result_type'] == 'default'
    assert payload['task_ids'] == [419, 418]
    assert payload['page'] == 2 and payload['per_page'] == 200


def test_gateway_select_all_passes_same_filters(gateway):
    """select-all 接受同一组过滤参数（与列表同口径）。"""
    fake, adapter = gateway
    adapter.set_current_request(_FakeRequest(json_body={
        'task_ids': [419], 'api_ids': '7', 'result_type': 'asr',
    }))
    from api_gateway.application.services.task.cherry_pick_service import CherryPickService
    body, code = CherryPickService.select_all_candidates()
    assert code == 200
    payload = fake.calls[0]
    assert payload['api_ids'] == [7]
    assert payload['result_type'] == 'asr'
    assert payload['select_all'] is True

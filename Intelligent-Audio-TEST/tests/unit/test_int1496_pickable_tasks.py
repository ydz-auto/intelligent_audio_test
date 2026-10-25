# -*- coding: utf-8 -*-
"""INT-1496 专项：挑选向导阶段 1「可挑选任务清单」端点（设计文档 §8.1）。

覆盖：
- 入选口径：终态任务 + 有可挑结果行（excluded=0）+ 未删除；容器/无结果任务不入
- 任务级字段口径：execution_status 是**任务**状态、created_at 是**任务**创建时间
  （不是结果级状态 / 首条结果时间）
- 聚合与计数：pickable_count = 该任务 excluded=0 结果行数（与 candidates 同口径）
- 服务端分页：total 不受 per_page 影响；page 1/2 无重复无遗漏；越界页 total 仍正确
- 排序：sort_by=status（completed→failed→stopped，同权重按任务名）/ name /
  created_at，sort_order 双向生效，`t.id` 兜底稳定
- 过滤：status 三终态、keyword 只匹配任务名（不匹配任务 ID）
- 可见性（INT-423）：非 owner 非 admin 看不到他人私有任务
- 网关侧：参数校验（枚举/分页越界 → 400）与透传，不聚合

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all，用例内自行清理，
对齐 test_int339_cherry_pick 口径。
"""
import os
from datetime import datetime, timedelta

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///./TEMP/int1496_proc.db')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from shared.infrastructure.user_context import (
    set_current_user_id, set_current_user_is_admin,
)

_TABLES = None

_OWNER = 42
_OTHER = 43
_ADMIN = 99


def _ensure_tables():
    global _TABLES
    if _TABLES is None:
        init_db(pool_size=2)
        from task_service.infrastructure.persistence.models import (
            Task, TestResult, TaskCherryPickRelation,
        )
        _TABLES = [t.__table__ for t in (Task, TestResult, TaskCherryPickRelation)]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


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
    set_current_user_id(None)
    set_current_user_is_admin(False)


def _seed_task(name, status='completed', owner=_OWNER, visibility='shared',
               created_at=None, results=2, excluded=0, deleted=False):
    """种子任务 + 结果行（results 条，其中 excluded 条标记排除）。"""
    from task_service.infrastructure.persistence.models import Task, TestResult
    session = get_db_session()
    try:
        task = Task(
            name=name, status=status, total_cases=results,
            created_by_user_id=owner, visibility=visibility,
            deleted=deleted,
            created_at=created_at or datetime(2026, 10, 20, 8, 0, 0),
        )
        session.add(task)
        session.flush()
        for i in range(results):
            session.add(TestResult(
                task_id=task.id, test_case_id=f'{name}-C{i}', device_id=7,
                execution_status='completed',
                excluded=1 if i < excluded else 0,
            ))
        session.commit()
        return task.id
    finally:
        remove_db_session()


def _query(**kwargs):
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    return cherry_pick_service.pickable_tasks(kwargs)


# ==================== 入选口径与字段语义 ====================

def test_lists_only_finished_tasks_with_pickable_results(db):
    """只收终态 + 未删除 + 至少一条 excluded=0 结果的行。"""
    done = _seed_task('完成的任务', status='completed')
    failed = _seed_task('失败的任务', status='failed')
    stopped = _seed_task('停止的任务', status='stopped')
    _seed_task('执行中的任务', status='running')
    _seed_task('无结果的任务', status='completed', results=0)
    _seed_task('已删任务', status='completed', deleted=True)
    _seed_task('全排除任务', status='completed', results=2, excluded=2)

    resp = _query()
    assert resp['success'] is True
    ids = [item['id'] for item in resp['data']['items']]
    assert ids == [done, failed, stopped]
    assert resp['data']['total'] == 3


def test_item_fields_are_task_level(db):
    """execution_status/created_at 取任务级字段（不是结果级 / 首条结果时间）。"""
    created = datetime(2026, 1, 2, 3, 4, 5)
    task_id = _seed_task('字段口径任务', status='failed', created_at=created, results=2)

    item = _query()['data']['items'][0]
    assert item['id'] == task_id
    assert item['name'] == '字段口径任务'
    assert item['execution_status'] == 'failed'   # 任务状态，不是结果行状态
    assert item['created_at'] == created.isoformat()
    assert set(item) == {'id', 'name', 'execution_status', 'pickable_count', 'created_at'}


def test_pickable_count_matches_candidates_scope(db):
    """pickable_count 与 candidates 同口径：excluded=0 的结果行数。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    task_id = _seed_task('计数任务', results=5, excluded=2)
    item = _query()['data']['items'][0]
    assert item['pickable_count'] == 3

    cand = cherry_pick_service.list_candidates({
        'task_ids': [task_id], 'page': 1, 'per_page': 200,
    })
    assert cand['success'] is True
    assert cand['data']['total'] == item['pickable_count']


# ==================== 分页 ====================

def test_pagination_is_server_side_and_total_independent(db):
    """page 1/2 无重复无遗漏；total 不随 per_page 变化；越界页 total 仍正确。"""
    created = datetime(2026, 10, 21, 8, 0, 0)
    ids = [_seed_task(f'分页任务{i}', status='completed',
                      created_at=created + timedelta(minutes=i), results=1)
           for i in range(5)]

    full = _query(per_page=50)['data']
    assert full['total'] == 5 and len(full['items']) == 5

    p1 = _query(page=1, per_page=2, sort_by='name')['data']
    p2 = _query(page=2, per_page=2, sort_by='name')['data']
    p3 = _query(page=3, per_page=2, sort_by='name')['data']
    seen = [i['id'] for i in p1['items'] + p2['items'] + p3['items']]
    assert sorted(seen) == sorted(ids) and len(seen) == len(set(seen))
    assert all(page['total'] == 5 for page in (p1, p2, p3))

    beyond = _query(page=9, per_page=2)['data']
    assert beyond['items'] == [] and beyond['total'] == 5

    wide = _query(page=1, per_page=200)['data']
    assert wide['total'] == 5


# ==================== 排序 ====================

def test_sort_by_status_weight_then_name(db):
    """status 排序权重 completed→failed→stopped；同权重按任务名；id 兜底。"""
    _seed_task('b失败', status='failed')
    _seed_task('z完成', status='completed')
    _seed_task('a完成', status='completed')
    _seed_task('c停止', status='stopped')

    asc = [i['name'] for i in _query(sort_by='status', sort_order='asc')['data']['items']]
    assert asc == ['a完成', 'z完成', 'b失败', 'c停止']

    desc = [i['name'] for i in _query(sort_by='status', sort_order='desc')['data']['items']]
    assert desc == ['c停止', 'b失败', 'z完成', 'a完成']


def test_sort_by_name_and_created_at_both_directions(db):
    base = datetime(2026, 9, 1, 0, 0, 0)
    _seed_task('乙任务', created_at=base)
    _seed_task('甲任务', created_at=base + timedelta(days=1))
    _seed_task('丙任务', created_at=base + timedelta(days=2))

    names_asc = [i['name'] for i in _query(sort_by='name', sort_order='asc')['data']['items']]
    names_desc = [i['name'] for i in _query(sort_by='name', sort_order='desc')['data']['items']]
    assert names_desc == list(reversed(names_asc))

    times_desc = [i['created_at'] for i in
                  _query(sort_by='created_at', sort_order='desc')['data']['items']]
    assert times_desc == sorted(times_desc, reverse=True)
    times_asc = [i['created_at'] for i in
                 _query(sort_by='created_at', sort_order='asc')['data']['items']]
    assert times_asc == sorted(times_asc)


# ==================== 过滤 ====================

def test_status_filter(db):
    _seed_task('完成任务', status='completed')
    _seed_task('失败任务', status='failed')
    _seed_task('停止任务', status='stopped')

    resp = _query(status='failed')['data']
    assert resp['total'] == 1 and resp['items'][0]['name'] == '失败任务'


def test_keyword_matches_task_name_only(db):
    """keyword 只匹配任务名，不匹配任务 ID（与 §8.1 口径一致）。"""
    kept = _seed_task('语音识别回归', status='completed')
    _seed_task('翻译回归', status='completed')

    resp = _query(keyword='语音')['data']
    assert [i['id'] for i in resp['items']] == [kept]

    # 用任务 ID 数字搜索不应命中（任务名不含该数字）
    assert _query(keyword=str(kept))['data']['items'] == []


# ==================== 可见性（INT-423） ====================

def test_visibility_private_task_hidden_from_others(db):
    shared = _seed_task('共享任务', visibility='shared', owner=_OTHER)
    own_private = _seed_task('我的私有任务', visibility='private', owner=_OWNER)
    _seed_task('他人私有任务', visibility='private', owner=_OTHER)

    set_current_user_id(_OWNER)
    set_current_user_is_admin(False)
    ids = [i['id'] for i in _query()['data']['items']]
    assert ids == [own_private, shared] or set(ids) == {own_private, shared}
    assert len(ids) == 2

    # admin 可见全部
    set_current_user_id(_ADMIN)
    set_current_user_is_admin(True)
    assert _query()['data']['total'] == 3


# ==================== 网关侧（参数校验 + 透传，不聚合） ====================

class _FakeRequest:
    def __init__(self, query_params=None):
        self.query_params = query_params or {}


class _FakeAcl:
    def __init__(self):
        self.calls = []

    def list_pickable_tasks(self, query):
        self.calls.append(query)
        from api_gateway.domain.dto import CommandResultDTO
        return CommandResultDTO(success=True, data={
            'items': [], 'total': 0, 'page': query['page'], 'per_page': query['per_page']})


@pytest.fixture()
def gateway(monkeypatch):
    """替换网关 ACL，捕获透传参数（校验失败时 ACL 不应被调用）。"""
    from api_gateway.infrastructure import request_adapter
    from api_gateway.application.services.task import cherry_pick_service as svc_mod

    fake = _FakeAcl()
    monkeypatch.setattr(svc_mod, '_cherry_pick_acl', fake)
    request_adapter.set_current_request(_FakeRequest())
    yield fake, request_adapter
    request_adapter.set_current_request(None)


def test_gateway_defaults_and_passthrough(gateway):
    fake, _ = gateway
    body, code = _gw_list()
    assert code == 200 and body.get('success') is True
    assert fake.calls == [{
        'keyword': None, 'status': None, 'sort_by': 'status',
        'sort_order': 'asc', 'page': 1, 'per_page': 50,
    }]


def test_gateway_passes_valid_params(gateway):
    fake, adapter = gateway
    adapter.set_current_request(_FakeRequest({
        'keyword': ' 语音 ', 'status': 'failed',
        'sort_by': 'created_at', 'sort_order': 'desc',
        'page': '2', 'per_page': '200',
    }))
    body, code = _gw_list()
    assert code == 200
    assert fake.calls[0] == {
        'keyword': '语音', 'status': 'failed', 'sort_by': 'created_at',
        'sort_order': 'desc', 'page': 2, 'per_page': 200,
    }


@pytest.mark.parametrize('params', [
    {'status': 'running'},          # 非三终态
    {'sort_by': 'status_weight'},   # 非法排序键
    {'sort_order': 'up'},           # 非法排序方向
    {'per_page': '201'},            # 越界（candidates 同口径 1–200）
    {'page': '0'},
])
def test_gateway_rejects_invalid_params(gateway, params):
    fake, adapter = gateway
    adapter.set_current_request(_FakeRequest(params))
    _body, code = _gw_list()
    assert code == 400
    assert fake.calls == []  # 校验失败不下发 gRPC


def _gw_list():
    from api_gateway.application.services.task.cherry_pick_service import CherryPickService
    return CherryPickService.list_pickable_tasks()

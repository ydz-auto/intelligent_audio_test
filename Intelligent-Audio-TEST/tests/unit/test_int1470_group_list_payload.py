# -*- coding: utf-8 -*-
"""INT-1470 分组列表响应体积优化单测。

- 默认页大小：100 → 40（无 per_page 时 data.per_page == 40，响应体积 21.4KB → ~8.9KB）；
  显式 per_page 不受影响（前端 React 传 200 / 新 Vue 传 100~1000）。
- 精简投影：`?fields=summary` 仅返回 id/name/test_case_count；
  默认（unset/full）保持完整 GroupItem 形状（编辑弹窗回显 description/algorithm_type）。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

from api_gateway.infrastructure.request_adapter import set_current_request  # noqa: E402

FULL_KEYS = {'id', 'name', 'description', 'algorithm_type', 'created_at',
             'updated_at', 'test_case_count'}
SUMMARY_KEYS = {'id', 'name', 'test_case_count'}


def _fake_request(query=None):
    state = SimpleNamespace(_json_body=None, _files={}, _form_data={})
    return SimpleNamespace(state=state, query_params=query or {},
                           method='GET', is_json=False, headers={})


def _groups(n):
    """构造 n 个分组（名称/描述带真实量级，便于体积核算）。

    test_case_count 由 task_service ListTestCaseGroups 一并返回（INT-1470 P1）。
    """
    return [{'id': f'00000000-0000-0000-0000-{i:012d}',
             'name': f'分组_{i}',
             'description': f'第 {i} 个分组的描述文本，用于校验列表投影字段',
             'algorithm_type': '',
             'test_case_count': 2} for i in range(n)]


def _run(monkeypatch, query, total_groups=127):
    import api_gateway.application.services.group_service as group_mod
    import api_gateway.infrastructure.grpc_proxies as proxies_pkg

    captured = {'stats_calls': 0, 'list_calls': []}
    groups = _groups(total_groups)

    class _StubTds:
        def list_testcase_groups(self, algorithm_type=None, search=None,
                                 page=0, per_page=0):
            captured['list_calls'].append(
                {'algorithm_type': algorithm_type, 'page': page,
                 'per_page': per_page})
            # 模拟 task_service 分页下推：page/per_page 缺省返回全量
            if page and per_page:
                start = (page - 1) * per_page
                return {'items': groups[start:start + per_page],
                        'total': len(groups)}
            return {'items': groups, 'total': len(groups)}

        def get_testcase_stats(self, **kwargs):
            captured['stats_calls'] += 1
            captured['stats_kwargs'] = kwargs
            # 每个分组 2 条用例，保证计数链路被走到
            return {'items': [{'key': g['id'], 'count': 2} for g in groups]}

    monkeypatch.setattr(proxies_pkg, 'task_data_service', _StubTds())
    set_current_request(_fake_request(query=query))
    try:
        payload, http_code = group_mod.GroupService.get_all()
    finally:
        set_current_request(None)
    return payload, http_code, captured


def test_default_page_size_is_40(monkeypatch):
    """无 per_page 时默认 40 条/页（INT-1470：原 100 导致单次 21.4KB）。"""
    payload, _, _ = _run(monkeypatch, query={})
    data = payload['data']
    assert data['per_page'] == 40
    assert len(data['items']) == 40
    assert data['total'] == 127
    assert data['pages'] == 4  # ceil(127 / 40)


def test_explicit_per_page_not_affected(monkeypatch):
    """前端显式传 per_page（React 200）仍按原样生效。"""
    payload, _, _ = _run(monkeypatch, query={'per_page': '200'})
    data = payload['data']
    assert data['per_page'] == 200
    assert len(data['items']) == 127


def test_default_projection_keeps_full_item(monkeypatch):
    """默认投影保持完整 GroupItem（编辑弹窗回显 description/algorithm_type 依赖）。"""
    payload, _, _ = _run(monkeypatch, query={})
    item = payload['data']['items'][0]
    assert set(item) == FULL_KEYS
    assert item['description'].startswith('第 0 个分组')
    assert item['test_case_count'] == 2


def test_summary_projection_minimal_fields(monkeypatch):
    """fields=summary 仅返回 id/name/test_case_count，体积最小化。"""
    payload, _, _ = _run(monkeypatch, query={'fields': 'summary'})
    data = payload['data']
    assert data['per_page'] == 40
    assert len(data['items']) == 40
    assert set(data['items'][0]) == SUMMARY_KEYS
    assert data['items'][0]['test_case_count'] == 2
    assert data['total'] == 127


def test_summary_projection_honors_page(monkeypatch):
    """summary 投影与分页组合：第二页返回对应切片。"""
    payload, _, _ = _run(monkeypatch, query={'fields': 'summary', 'page': '2', 'per_page': '10'})
    items = payload['data']['items']
    assert len(items) == 10
    assert items[0]['name'] == '分组_10'
    assert [i['test_case_count'] for i in items] == [2] * 10


def test_unknown_fields_value_falls_back_to_full(monkeypatch):
    """未知 fields 值回退完整投影（不静默丢字段）。"""
    payload, _, _ = _run(monkeypatch, query={'fields': 'whatever'})
    assert set(payload['data']['items'][0]) == FULL_KEYS


# ---- INT-1470 P1：默认口径单次 gRPC（计数随列表带回） ----


def test_default_path_is_single_rpc(monkeypatch):
    """默认口径（无筛选/非收藏/非回收站）不再发第二次聚合 RPC，
    计数直接取 ListTestCaseGroups 带回的 test_case_count。"""
    payload, _, captured = _run(monkeypatch, query={})
    assert captured['stats_calls'] == 0
    assert payload['data']['items'][0]['test_case_count'] == 2


# ---- INT-1470 分页下推：默认/algorithm_type 口径只拉当前页 ----


def test_default_path_pushes_pagination(monkeypatch):
    """默认口径把 page/per_page 下推给 ListTestCaseGroups，不再全量拉取。"""
    payload, _, captured = _run(monkeypatch, query={'page': '2', 'per_page': '10'})
    assert captured['list_calls'] == [
        {'algorithm_type': None, 'page': 2, 'per_page': 10}]
    data = payload['data']
    assert data['total'] == 127
    assert data['pages'] == 13
    assert len(data['items']) == 10
    assert data['items'][0]['name'] == '分组_10'
    assert [i['test_case_count'] for i in data['items']] == [2] * 10


def test_algorithm_type_filter_also_pushed_down(monkeypatch):
    """algorithm_type 筛选口径同样下推分页（分组集合由 SQL 直接确定）。"""
    payload, _, captured = _run(monkeypatch, query={'algorithm_type': 'asr'})
    assert captured['list_calls'] == [
        {'algorithm_type': 'asr', 'page': 1, 'per_page': 40}]
    assert captured['stats_calls'] == 0
    assert payload['data']['total'] == 127


def test_case_filter_path_does_not_push_pagination(monkeypatch):
    """用例级筛选需先聚合确定分组集合，不得下推分页（保持现状）。"""
    _, _, captured = _run(monkeypatch, query={'keyword': 'ui405'})
    assert captured['list_calls'] == [
        {'algorithm_type': None, 'page': 0, 'per_page': 0}]
    assert captured['stats_calls'] == 1


def test_favorite_path_does_not_push_pagination(monkeypatch):
    """收藏口径仍需用例级过滤，保持原路径（全量列表 + 聚合 RPC）。"""
    _, _, captured = _run(monkeypatch, query={'favorite': 'true'})
    assert captured['list_calls'] == [
        {'algorithm_type': None, 'page': 0, 'per_page': 0}]
    assert captured['stats_calls'] == 1


def test_invalid_pagination_params_fall_back_to_default(monkeypatch):
    """per_page/page <= 0 归一为默认页，避免下推被当作「不分页」返回全量。"""
    payload, _, captured = _run(monkeypatch, query={'page': '0', 'per_page': '0'})
    assert captured['list_calls'] == [
        {'algorithm_type': None, 'page': 1, 'per_page': 40}]
    assert payload['data']['per_page'] == 40
    assert len(payload['data']['items']) == 40


def test_favorite_path_keeps_stats_rpc(monkeypatch):
    """收藏口径需用例级过滤，仍走聚合统计 RPC（不得退化为列表内计数）。"""
    payload, _, captured = _run(monkeypatch, query={'favorite': 'true'})
    assert captured['stats_calls'] == 1
    assert captured['stats_kwargs'].get('favorite') is True


def test_only_deleted_path_keeps_stats_rpc(monkeypatch):
    """回收站口径同样走聚合统计 RPC。"""
    _, _, captured = _run(monkeypatch, query={'only_deleted': 'true'})
    assert captured['stats_calls'] == 1
    assert captured['stats_kwargs'].get('deleted') is True


def test_case_filter_path_keeps_stats_rpc(monkeypatch):
    """用例级筛选（keyword/type/dimension）仍走聚合统计 RPC。"""
    _, _, captured = _run(monkeypatch, query={'keyword': 'ui405'})
    assert captured['stats_calls'] == 1
    assert captured['stats_kwargs'].get('group_by') == 'group_id'


# ---- INT-1470 分页下推：task_service 仓储口径 ----


@pytest.fixture(scope='module')
def pagination_db():
    """真实文件型 sqlite：7 个分组 + 用例，用于分页下推与计数收敛断言。"""
    import uuid as _uuid

    from shared.models.database import (
        init_db, get_db_session, get_engine, remove_db_session,
    )
    from task_service.infrastructure.persistence.models import TestCase, TestCaseGroup

    init_db(pool_size=3)
    remove_db_session()
    from shared.models.database import Base
    engine = get_engine()
    Base.metadata.create_all(
        bind=engine, tables=[TestCaseGroup.__table__, TestCase.__table__])

    run = _uuid.uuid4().hex[:8]
    algo = f'int1470_{run}'
    other_algo = f'int1470_other_{run}'
    session = get_db_session()
    group_ids = []
    for i in range(7):
        gid = f'int1470_{run}_g{i}'
        group_ids.append(gid)
        session.add(TestCaseGroup(
            id=gid, name=f'分页组_{i}_{run}', algorithm_type=algo,
            description=f'第 {i} 组'))
    session.flush()

    # g0：3 条活跃用例（含 1 条软删不计）；g1：2 条本算法 + 1 条其他算法
    cases = [
        (f'c0a_{run}', group_ids[0], algo, False),
        (f'c0b_{run}', group_ids[0], algo, False),
        (f'c0c_{run}', group_ids[0], algo, False),
        (f'c0d_{run}', group_ids[0], algo, True),
        (f'c1a_{run}', group_ids[1], algo, False),
        (f'c1b_{run}', group_ids[1], algo, False),
        (f'c1c_{run}', group_ids[1], other_algo, False),
    ]
    for cid, gid, case_algo, deleted in cases:
        session.add(TestCase(
            id=cid, name=f'用例_{cid}', config={}, group_id=gid,
            algorithm_type=case_algo, deleted=deleted))
    session.commit()
    session.close()
    yield {'algo': algo, 'other_algo': other_algo, 'group_ids': group_ids}
    # 清理本夹具数据：同进程其他测试文件共用 conftest 临时库，残留行会污染
    # 它们的聚合断言（INT-1470 实测：int146 stats total 被本夹具行数带偏）
    session = get_db_session()
    session.query(TestCase).filter(
        TestCase.id.like(f'%_{run}%')).delete(synchronize_session=False)
    session.query(TestCaseGroup).filter(
        TestCaseGroup.id.like(f'int1470_{run}%')).delete(synchronize_session=False)
    session.commit()
    session.close()
    remove_db_session()


def test_paginated_returns_only_current_page(pagination_db):
    """page/per_page 生效：只返回当前页，total 为过滤后分组总数。"""
    from task_service.infrastructure.persistence._testcase_group_mixin import (
        TestCaseGroupMixin,
    )
    repo = TestCaseGroupMixin()
    result = repo.list_groups_page(algorithm_type=pagination_db['algo'],
                                   page=2, per_page=3)
    assert result['total'] == 7
    assert [g['id'] for g in result['items']] == pagination_db['group_ids'][3:6]


def test_pages_cover_all_groups_without_duplicates(pagination_db):
    """逐页拉取：id 去重后数量 == total，无重复无丢失。"""
    from task_service.infrastructure.persistence._testcase_group_mixin import (
        TestCaseGroupMixin,
    )
    repo = TestCaseGroupMixin()
    seen = []
    for page in (1, 2, 3):
        result = repo.list_groups_page(algorithm_type=pagination_db['algo'],
                                       page=page, per_page=3)
        seen.extend(g['id'] for g in result['items'])
    assert len(seen) == len(set(seen)) == 7
    assert set(seen) == set(pagination_db['group_ids'])


def test_counts_only_current_page_and_same_scope(pagination_db):
    """计数只算当前页分组：未删除用例计数，软删与其他算法类型用例不计。"""
    from task_service.infrastructure.persistence._testcase_group_mixin import (
        TestCaseGroupMixin,
    )
    repo = TestCaseGroupMixin()
    result = repo.list_groups_page(algorithm_type=pagination_db['algo'],
                                   page=1, per_page=2)
    counts = {g['id']: g['test_case_count'] for g in result['items']}
    assert counts == {
        pagination_db['group_ids'][0]: 3,  # 3 活跃；软删 1 条不计
        pagination_db['group_ids'][1]: 2,  # 其他算法类型 1 条不计
    }


def test_count_aggregation_scope_is_page_ids(pagination_db, monkeypatch):
    """计数聚合的 group_id 集合 == 当前页分组 id 集合（不下推全量）。"""
    from task_service.infrastructure.persistence._testcase_group_mixin import (
        TestCaseGroupMixin,
    )
    repo = TestCaseGroupMixin()
    captured = {}
    original = repo._count_group_matched_cases

    def spy(session, dimension_id, keyword, algorithm_type='', group_ids=None):
        captured['group_ids'] = list(group_ids) if group_ids is not None else None
        return original(session, dimension_id, keyword,
                        algorithm_type=algorithm_type, group_ids=group_ids)

    monkeypatch.setattr(repo, '_count_group_matched_cases', spy)
    result = repo.list_groups_page(algorithm_type=pagination_db['algo'],
                                   page=2, per_page=3)
    assert captured['group_ids'] == [g['id'] for g in result['items']]
    assert len(captured['group_ids']) == 3


def test_unpaginated_behavior_unchanged(pagination_db):
    """旧调用方不传 page/per_page：返回全量，total == len(items)。"""
    from task_service.infrastructure.persistence._testcase_group_mixin import (
        TestCaseGroupMixin,
    )
    repo = TestCaseGroupMixin()
    result = repo.list_groups_page(algorithm_type=pagination_db['algo'])
    assert result['total'] == len(result['items']) == 7
    # list_groups 旧接口仍返回纯列表（home_service / stats_cache / MCP 口径）
    legacy = repo.list_groups(algorithm_type=pagination_db['algo'])
    assert isinstance(legacy, list)
    assert [g['id'] for g in legacy] == pagination_db['group_ids']

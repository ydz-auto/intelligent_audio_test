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

from api_gateway.infrastructure.request_adapter import set_current_request  # noqa: E402

FULL_KEYS = {'id', 'name', 'description', 'algorithm_type', 'created_at',
             'updated_at', 'test_case_count'}
SUMMARY_KEYS = {'id', 'name', 'test_case_count'}


def _fake_request(query=None):
    state = SimpleNamespace(_json_body=None, _files={}, _form_data={})
    return SimpleNamespace(state=state, query_params=query or {},
                           method='GET', is_json=False, headers={})


def _groups(n):
    """构造 n 个分组（名称/描述带真实量级，便于体积核算）。"""
    return [{'id': f'00000000-0000-0000-0000-{i:012d}',
             'name': f'分组_{i}',
             'description': f'第 {i} 个分组的描述文本，用于校验列表投影字段',
             'algorithm_type': ''} for i in range(n)]


def _run(monkeypatch, query, total_groups=127):
    import api_gateway.application.services.group_service as group_mod
    import api_gateway.infrastructure.grpc_proxies as proxies_pkg

    captured = {}
    groups = _groups(total_groups)

    class _StubTds:
        def list_testcase_groups(self, algorithm_type=None, search=None):
            return {'items': groups}

        def get_testcase_stats(self, **kwargs):
            captured['stats_kwargs'] = kwargs
            # 每个分组 2 条用例，保证计数链路被走到
            return {'items': [{'key': g['id'], 'count': 2} for g in groups]}

    monkeypatch.setattr(proxies_pkg, 'task_data_service', _StubTds())
    set_current_request(_fake_request(query=query))
    try:
        payload, http_code = group_mod.GroupService.get_all()
    finally:
        set_current_request(None)
    return payload, http_code


def test_default_page_size_is_40(monkeypatch):
    """无 per_page 时默认 40 条/页（INT-1470：原 100 导致单次 21.4KB）。"""
    payload, _ = _run(monkeypatch, query={})
    data = payload['data']
    assert data['per_page'] == 40
    assert len(data['items']) == 40
    assert data['total'] == 127
    assert data['pages'] == 4  # ceil(127 / 40)


def test_explicit_per_page_not_affected(monkeypatch):
    """前端显式传 per_page（React 200）仍按原样生效。"""
    payload, _ = _run(monkeypatch, query={'per_page': '200'})
    data = payload['data']
    assert data['per_page'] == 200
    assert len(data['items']) == 127


def test_default_projection_keeps_full_item(monkeypatch):
    """默认投影保持完整 GroupItem（编辑弹窗回显 description/algorithm_type 依赖）。"""
    payload, _ = _run(monkeypatch, query={})
    item = payload['data']['items'][0]
    assert set(item) == FULL_KEYS
    assert item['description'].startswith('第 0 个分组')
    assert item['test_case_count'] == 2


def test_summary_projection_minimal_fields(monkeypatch):
    """fields=summary 仅返回 id/name/test_case_count，体积最小化。"""
    payload, _ = _run(monkeypatch, query={'fields': 'summary'})
    data = payload['data']
    assert data['per_page'] == 40
    assert len(data['items']) == 40
    assert set(data['items'][0]) == SUMMARY_KEYS
    assert data['items'][0]['test_case_count'] == 2
    assert data['total'] == 127


def test_summary_projection_honors_page(monkeypatch):
    """summary 投影与分页组合：第二页返回对应切片。"""
    payload, _ = _run(monkeypatch, query={'fields': 'summary', 'page': '2', 'per_page': '10'})
    items = payload['data']['items']
    assert len(items) == 10
    assert items[0]['name'] == '分组_10'
    assert [i['test_case_count'] for i in items] == [2] * 10


def test_unknown_fields_value_falls_back_to_full(monkeypatch):
    """未知 fields 值回退完整投影（不静默丢字段）。"""
    payload, _ = _run(monkeypatch, query={'fields': 'whatever'})
    assert set(payload['data']['items'][0]) == FULL_KEYS

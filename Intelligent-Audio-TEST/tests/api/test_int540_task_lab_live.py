# -*- coding: utf-8 -*-
"""INT-540 验收（拆分④）：任务 lab_ids + /tasks/validate + 关联实验室 集成冒烟。

依赖实机栈（tests/api/conftest.py 门禁）：
- RUN_LIVE_STACK=1 且栈已切隔离测试库（INT-246）才执行；默认回归 skip。
- laboratories / task_laboratory_relations 表经 docker bootstrap 链（INT-537 已纳入
  add_laboratory_tables）就绪；INT-538/539 RPC（设备/播放设备/用例 lab 透出）就绪。

覆盖（验收标准 3/4）：
- 带 lab_ids 建任务成功且响应内联 labs；GET /tasks/{id}/labs 返回（多实验室 N:M）
- /tasks/validate 正反例：用例通用可通过、越域设备拒绝、lab_ids 不存在
- 回归：无 lab_ids 建任务正常（lab_ids 可选缺省）

用例自清理：创建的任务/实验室在测试内软删/清理，避免污染隔离测试库。
"""
import os
import uuid

import pytest

API = 'http://127.0.0.1:5000/api/v1'


@pytest.fixture(scope='module')
def api(api_client):
    return api_client


def _base_headers():
    # tests/api 网关处于 AUTH_MODE=off 时中间件注入通配 *（admin），读写均放行
    return {}


def _make_lab(api, code):
    resp = api.post('/laboratories', json={
        'code': code, 'name': f'INT-540 冒烟 {code}', 'status': 'active',
    }, headers=_base_headers())
    assert resp.status_code == 201, f'建实验室失败: {resp.text[:300]}'
    return resp.json()['data']['id']


def _make_case(api, case_id, lab_id=None):
    """经用例 CRUD 建用例；lab_id 写进 config JSONB（专属/通用）。

    后端强制 group_id/group（创建时缺少直接 400，见 tests/ui/utils/api_client.py
    create_testcase 同口径），此处补默认分组。
    """
    config = {'rounds': []}
    if lab_id is not None:
        config['lab_id'] = lab_id
    resp = api.post('/testcases', json={
        'name': f'INT-540 用例 {case_id}',
        'config': config,
        'group': 'INT-540 冒烟分组',
    }, headers=_base_headers())
    assert resp.status_code == 201, f'建用例失败: {resp.text[:300]}'
    # 返回 API 实际生成的用例 ID（UUID），不是入参 name 片段
    return resp.json()['data']['id']


def test_task_create_with_lab_ids_returns_labs(api):
    """带 lab_ids 建任务成功且响应内联 labs；GET /tasks/{id}/labs 一致。"""
    uid = uuid.uuid4().hex[:8]
    lab_a = _make_lab(api, f'INT540A-{uid}')
    lab_b = _make_lab(api, f'INT540B-{uid}')

    resp = api.post('/tasks', json={
        'name': f'INT-540 跨实验室任务 {uid}',
        'case_ids': [],
        'device_ids': [],
        'lab_ids': [lab_a, lab_b],
    }, headers=_base_headers())
    assert resp.status_code == 201, f'建任务失败: {resp.text[:300]}'
    body = resp.json()
    assert body.get('success') is True
    data = body['data']
    assert data['id'] > 0
    assert 'labs' in data, '任务创建响应应内联 labs'
    lab_ids = {lab['id'] for lab in data['labs']}
    assert {lab_a, lab_b} <= lab_ids, f'labs 缺失: {data["labs"]}'

    try:
        # GET /tasks/{id}/labs → 多实验室 N:M
        resp = api.get(f'/tasks/{data["id"]}/labs', headers=_base_headers())
        assert resp.status_code == 200, resp.text[:300]
        labs = resp.json()['data']['labs']
        assert {l['id'] for l in labs} == {lab_a, lab_b}

        # 任务列表/详情内联 labs
        resp = api.get(f'/tasks/{data["id"]}', headers=_base_headers())
        assert resp.status_code == 200
        assert {l['id'] for l in resp.json()['data']['labs']} == {lab_a, lab_b}
    finally:
        api.delete(f'/tasks/{data["id"]}', headers=_base_headers())
        api.delete(f'/laboratories/{lab_a}', headers=_base_headers())
        api.delete(f'/laboratories/{lab_b}', headers=_base_headers())


def test_validate_generic_case_passes_cross_domain_device_rejected(api):
    """/tasks/validate：通用用例可通过、越域设备拒绝、lab_ids 不存在报错。"""
    uid = uuid.uuid4().hex[:8]
    lab = _make_lab(api, f'INT540V-{uid}')
    case_id = _make_case(api, f'INT540-c-{uid}', lab_id=None)  # 通用用例
    try:
        # 正例：通用用例 + 无设备 → valid
        resp = api.post('/tasks/validate', json={
            'lab_ids': [lab],
            'case_ids': [case_id],
            'device_ids': [],
        }, headers=_base_headers())
        assert resp.status_code == 200, resp.text[:300]
        assert resp.json()['data']['valid'] is True
        assert resp.json()['data']['errors'] == []

        # 反例：越域设备（未绑定 lab_id → 拒绝）
        resp = api.post('/tasks/validate', json={
            'lab_ids': [lab],
            'device_ids': [999999],
        }, headers=_base_headers())
        assert resp.status_code == 200, resp.text[:300]
        data = resp.json()['data']
        assert data['valid'] is False
        assert any(e['resource_type'] == 'device' for e in data['errors'])

        # 反例：lab_ids 不存在
        resp = api.post('/tasks/validate', json={
            'lab_ids': [999999],
            'case_ids': [],
            'device_ids': [],
        }, headers=_base_headers())
        assert resp.status_code == 200, resp.text[:300]
        data = resp.json()['data']
        assert data['valid'] is False
        assert any(e['resource_type'] == 'laboratory' for e in data['errors'])
    finally:
        # 测试数据卫生：软删本用例创建的实验室（INT-540 隔离库不留残留）
        api.delete(f'/laboratories/{lab}', headers=_base_headers())


def test_task_create_without_lab_ids_regression(api):
    """回归：无 lab_ids 建任务正常，响应 labs=[]。"""
    uid = uuid.uuid4().hex[:8]
    resp = api.post('/tasks', json={
        'name': f'INT-540 普通任务 {uid}',
        'case_ids': [],
        'device_ids': [],
    }, headers=_base_headers())
    assert resp.status_code == 201, f'建任务失败: {resp.text[:300]}'
    data = resp.json()['data']
    assert data['labs'] == []
    api.delete(f'/tasks/{data["id"]}', headers=_base_headers())

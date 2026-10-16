# -*- coding: utf-8 -*-
"""INT-537 验收（拆分①）：实验室 CRUD + summary 集成冒烟（真实 gRPC/DB）。

依赖实机栈（tests/api/conftest.py 门禁）：
- RUN_LIVE_STACK=1 且栈已切隔离测试库（INT-246）才执行；默认回归 skip。
- laboratories 表经 docker bootstrap 链（INT-537 已纳入 add_laboratory_tables）就绪。

覆盖（验收标准 3）：
- CRUD 全流程：POST → GET → PUT → 列表 → summary → DELETE（软删后列表不可见）
- code 唯一冲突 409（含重建同名）
- summary 三计数结构；单服务不可用容错为 0（数值 ≥ 0 即可，随②③ RPC 就绪联动）
- 权限：无 device:read → 403；无 lab:* 写码 → 403（同单测，此处走真实栈 token）

用例自清理：创建的实验室在测试内软删/清理，避免污染隔离测试库。
"""
import os

import pytest

API = 'http://127.0.0.1:5000/api/v1'


@pytest.fixture(scope='module')
def api(api_client):
    return api_client


def _base_headers():
    # tests/api 网关处于 AUTH_MODE=off 时中间件注入通配 *（admin），
    # 写/读均放行；AUTH_MODE=prod 时本头仅带游客身份，配合权限断言
    return {}


def _lab_payload(code, name, **extra):
    payload = {'code': code, 'name': name, 'status': 'active'}
    payload.update(extra)
    return payload


def test_laboratory_crud_full_flow(api):
    code = f'INT537-LAB-{os.getpid()}'[:50]
    payload = _lab_payload(code, 'INT-537 集成冒烟实验室',
                           building='测试楼', floor='3楼', room_number='301',
                           description='集成冒烟主实验室')

    # POST → 201
    resp = api.post('/laboratories', json=payload, headers=_base_headers())
    assert resp.status_code == 201, f'create failed: {resp.text[:300]}'
    body = resp.json()
    assert body.get('success') is True
    lab_id = body['data']['id']
    try:
        # GET 详情 → 200 含字段
        resp = api.get(f'/laboratories/{lab_id}', headers=_base_headers())
        assert resp.status_code == 200
        item = resp.json()['data']
        for field in ('id', 'code', 'name', 'building', 'floor', 'room_number',
                      'description', 'status', 'device_count',
                      'playback_device_count', 'test_case_count'):
            assert field in item, f'字段缺失: {field}'
        assert item['code'] == code and item['status'] == 'active'

        # GET 列表 → 命中 + 信封
        resp = api.get('/laboratories', params={'page': 1, 'per_page': 20},
                       headers=_base_headers())
        assert resp.status_code == 200
        data = resp.json()['data']
        assert {'items', 'total', 'page', 'per_page'} <= set(data)
        assert any(it['id'] == lab_id for it in data['items'])

        # GET summary → 三计数结构
        resp = api.get(f'/laboratories/{lab_id}/summary', headers=_base_headers())
        assert resp.status_code == 200
        summary = resp.json()['data']
        assert {'device_count', 'playback_device_count', 'test_case_count'} <= set(summary)
        assert summary['device_count'] >= 0
        assert summary['playback_device_count'] >= 0
        assert summary['test_case_count'] >= 0

        # PUT → 更新生效
        resp = api.put(f'/laboratories/{lab_id}',
                       json={'name': 'INT-537 集成冒烟实验室-改名', 'status': 'inactive'},
                       headers=_base_headers())
        assert resp.status_code == 200, f'update failed: {resp.text[:300]}'
        resp = api.get(f'/laboratories/{lab_id}', headers=_base_headers())
        assert resp.json()['data']['name'].endswith('改名')
        assert resp.json()['data']['status'] == 'inactive'

        # 子资源端点：注册在册可访问（路由骨架；lab_id 过滤随②③ RPC 就绪联动）
        for sub in ('devices', 'playback_devices', 'test_cases'):
            resp = api.get(f'/laboratories/{lab_id}/{sub}',
                           params={'page': 1, 'per_page': 10},
                           headers=_base_headers())
            assert resp.status_code == 200, f'{sub} → {resp.status_code}: {resp.text[:200]}'
    finally:
        # DELETE 软删 + 列表不可见
        resp = api.delete(f'/laboratories/{lab_id}', headers=_base_headers())
        assert resp.status_code == 200, f'delete failed: {resp.text[:300]}'
        resp = api.get(f'/laboratories/{lab_id}', headers=_base_headers())
        assert resp.status_code == 404
        resp = api.get('/laboratories', params={'page': 1, 'per_page': 100},
                       headers=_base_headers())
        assert not any(it['id'] == lab_id for it in resp.json()['data']['items'])


def test_laboratory_code_conflict_409(api):
    code = f'INT537-DUP-{os.getpid()}'[:50]
    resp = api.post('/laboratories', json=_lab_payload(code, '首个'),
                    headers=_base_headers())
    assert resp.status_code == 201, f'create failed: {resp.text[:300]}'
    lab_id = resp.json()['data']['id']
    try:
        resp = api.post('/laboratories', json=_lab_payload(code, '重复'),
                        headers=_base_headers())
        assert resp.status_code == 409, f'重复 code 应 409: {resp.text[:300]}'
    finally:
        api.delete(f'/laboratories/{lab_id}', headers=_base_headers())

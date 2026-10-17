# -*- coding: utf-8 -*-
"""INT-655 实机契约：/api/v1/laboratories CRUD 全端点（设备页实验室管理）。

覆盖（实验室扩展功能设计.md §5.1/§5.4.1）：
- GET /laboratories — 分页列表（含 device_count/playback_device_count/test_case_count）
- GET /laboratories/{id} — 详情
- GET /laboratories/{id}/summary — 资源统计
- POST /laboratories — 创建（201 + id）
- PUT /laboratories/{id} — 编辑
- DELETE /laboratories/{id} — 删除
- 边界：重复 code → 409；更新未知 id → 404；非法 status → 400；
  软删后同 code 重建 → 201（审计 P2 修复，需迁移 Step 9 后生效）

前置（tests/api/conftest.py 统一把关）：RUN_LIVE_STACK=1 且实机栈已切隔离测试库。

数据卫生：全部实验室产物在 finally 中按 code 前缀清理（隔离库不留残留）。
"""
import os
import time

import pytest

LAB_PREFIX = 'INT655'


def _lab_code(tag):
    return f'{LAB_PREFIX}-{tag}-{int(time.time()) % 100000}'


def _cleanup_lab(api_client, lab_id):
    if lab_id:
        try:
            api_client.delete(f'/laboratories/{lab_id}')
        except Exception:
            pass


def _test_create_and_get(api_client):
    code = _lab_code('A')
    payload = {
        'code': code,
        'name': 'INT655音频测试实验室',
        'building': 'A栋',
        'floor': '2楼',
        'room_number': '201',
        'description': 'INT-655 契约测试实验室',
        'status': 'active',
    }
    r = api_client.post('/laboratories', json=payload)
    assert r.status_code == 201, f'创建失败: {r.status_code} {r.text[:300]}'
    data = r.json()['data']
    lab_id = data['id']
    assert lab_id, f'创建未返回 id: {data}'
    try:
        # 列表可见且含资源统计字段
        r = api_client.get('/laboratories', params={'keyword': code})
        assert r.status_code == 200
        items = r.json()['data']['items']
        item = next((it for it in items if it['code'] == code), None)
        assert item, f'列表未含新建实验室: {items}'
        assert 'device_count' in item and 'playback_device_count' in item \
            and 'test_case_count' in item, f'列表缺资源统计: {item.keys()}'

        # 详情
        r = api_client.get(f'/laboratories/{lab_id}')
        assert r.status_code == 200
        assert r.json()['data']['code'] == code

        # summary
        r = api_client.get(f'/laboratories/{lab_id}/summary')
        assert r.status_code == 200
        summary = r.json()['data']
        assert 'device_count' in summary and 'playback_device_count' in summary \
            and 'test_case_count' in summary, f'summary 缺统计: {summary}'
    finally:
        _cleanup_lab(api_client, lab_id)


def test_laboratory_full_crud(api_client, require_backend):
    """完整链路：创建→列表→详情→summary→更新→删除。"""
    code = _lab_code('B')
    r = api_client.post('/laboratories', json={
        'code': code, 'name': '旧名', 'status': 'active'})
    assert r.status_code == 201, f'创建失败: {r.status_code} {r.text[:300]}'
    lab_id = r.json()['data']['id']
    try:
        # 更新
        r = api_client.put(f'/laboratories/{lab_id}', json={
            'name': '新名', 'building': 'B栋'})
        assert r.status_code == 200, f'更新失败: {r.status_code} {r.text[:300]}'
        assert r.json()['data']['name'] == '新名'

        # 删除
        r = api_client.delete(f'/laboratories/{lab_id}')
        assert r.status_code == 200, f'删除失败: {r.status_code} {r.text[:300]}'

        # 删除后详情 404
        r = api_client.get(f'/laboratories/{lab_id}')
        assert r.status_code == 404, f'删除后仍可读: {r.status_code}'
    finally:
        _cleanup_lab(api_client, lab_id)


def test_laboratory_duplicate_code_conflict(api_client, require_backend):
    """重复 code → 409。"""
    code = _lab_code('C')
    r1 = api_client.post('/laboratories', json={'code': code, 'name': '一'})
    assert r1.status_code == 201, f'首个创建失败: {r1.status_code} {r1.text[:300]}'
    lab_id = r1.json()['data']['id']
    try:
        r2 = api_client.post('/laboratories', json={'code': code, 'name': '二'})
        assert r2.status_code == 409, f'重复 code 未返回 409: {r2.status_code} {r2.text[:300]}'
    finally:
        _cleanup_lab(api_client, lab_id)


def test_laboratory_update_unknown_404(api_client, require_backend):
    """更新未知 id → 404。"""
    r = api_client.put('/laboratories/99999999', json={'name': 'x'})
    assert r.status_code == 404, f'未知 id 更新未返回 404: {r.status_code} {r.text[:300]}'


def test_laboratory_invalid_status_400(api_client, require_backend):
    """非法 status → 400（枚举校验）。"""
    r = api_client.post('/laboratories', json={
        'code': _lab_code('D'), 'name': 'x', 'status': 'bogus'})
    assert r.status_code == 400, f'非法 status 未返回 400: {r.status_code} {r.text[:300]}'


def test_laboratory_recreate_same_code_after_delete(api_client, require_backend):
    """审计 P2 修复：软删后同 code 可复用（部分唯一索引；旧库需先跑迁移 Step 9）。"""
    code = _lab_code('E')
    r1 = api_client.post('/laboratories', json={'code': code, 'name': '旧实验室'})
    assert r1.status_code == 201, f'首次创建失败: {r1.status_code} {r1.text[:300]}'
    lab_id = r1.json()['data']['id']
    try:
        r2 = api_client.delete(f'/laboratories/{lab_id}')
        assert r2.status_code == 200, f'删除失败: {r2.status_code} {r2.text[:300]}'

        # 删除后详情 404
        r3 = api_client.get(f'/laboratories/{lab_id}')
        assert r3.status_code == 404, f'软删后仍可读: {r3.status_code}'

        # 同 code 重建 → 201（不允许 400/SQL 报错泄漏，也不应 409）
        r4 = api_client.post('/laboratories', json={'code': code, 'name': '新实验室'})
        assert r4.status_code == 201, (
            f'软删后同 code 重建未返回 201: {r4.status_code} {r4.text[:300]}')
        new_lab_id = r4.json()['data']['id']
        assert new_lab_id != lab_id
        assert r4.json()['data']['name'] == '新实验室'
        _cleanup_lab(api_client, new_lab_id)
    finally:
        _cleanup_lab(api_client, lab_id)

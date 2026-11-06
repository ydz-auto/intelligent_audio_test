# -*- coding: utf-8 -*-
"""任务数据导入导出 API 冒烟测试（INT-25）

对运行中的后端做轻量冒烟：路由存在性、错误分支、进度快照信封。
完整 roundtrip（导出→预检→导入→重映射校验）依赖库内有已完成任务，
放在联调环境执行；本文件在后端未运行或为旧进程时按 skip 机制跳过。
"""
import io
import zipfile

import pytest

from tests.api.conftest import API_BASE  # noqa: F401


def _unwrap(resp):
    # 平台信封契约：{success, code, message} 恒在；data/detail 有值才出现（None 省略）
    assert resp.status_code < 500, f'服务端错误: {resp.status_code} {resp.text[:300]}'
    body = resp.json()
    assert {'success', 'code', 'message'} <= set(body.keys()), f'信封缺失: {body}'
    return body


def _skip_if_stale_gateway(body):
    """运行中的网关为改动前启动的旧进程时（路由 404），跳过而非误判"""
    detail = str(body.get('detail') or '')
    if '404' in detail and 'not found' in detail.lower():
        pytest.skip('运行中的网关为旧进程（未注册 data-transfer 路由），重启后端后重试')


def test_import_progress_snapshot_envelope(api_client):
    """GET /import/progress 返回标准信封（新网关下无论 Redis 是否可用都 success，data 可为空）"""
    resp = api_client.get(f'{API_BASE}/data-transfer/import/progress')
    body = _unwrap(resp)
    _skip_if_stale_gateway(body)
    assert body['success'] is True


def test_export_empty_task_ids_rejected(api_client):
    """POST /export 空 task_ids 返回业务失败信封"""
    resp = api_client.post(f'{API_BASE}/data-transfer/export', json={'task_ids': []})
    body = _unwrap(resp)
    _skip_if_stale_gateway(body)
    assert body['success'] is False
    assert 'task_ids' in body['message']


def test_import_preview_rejects_non_zip(api_client):
    """POST /import/preview 非 ZIP 内容返回业务失败信封"""
    resp = api_client.post(
        f'{API_BASE}/data-transfer/import/preview',
        files={'file': ('not_a_zip.bin', io.BytesIO(b'plain text'), 'application/octet-stream')})
    body = _unwrap(resp)
    _skip_if_stale_gateway(body)
    assert body['success'] is False
    assert 'ZIP' in body['message']


def test_import_preview_rejects_bad_manifest(api_client):
    """POST /import/preview 合法 ZIP 但 manifest 版本不符 → 业务失败（拒绝导入）"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('manifest.json', '{"version": "9.9", "tasks": []}')
    buf.seek(0)
    resp = api_client.post(
        f'{API_BASE}/data-transfer/import/preview',
        files={'file': ('bad_version.zip', buf, 'application/zip')})
    body = _unwrap(resp)
    _skip_if_stale_gateway(body)
    assert body['success'] is False

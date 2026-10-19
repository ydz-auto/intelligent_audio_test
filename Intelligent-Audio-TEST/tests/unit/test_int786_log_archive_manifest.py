# -*- coding: utf-8 -*-
"""INT-786 日志归档全局文件清单接口（GET /logs/archive/logs 无筛选参数）回归。

覆盖（对照 INT-780 契约裁定）：
1. 服务层：无 task_id/test_case_id → 全局归档文件清单
   `data = {items:[{filename, sizeBytes, archivedAt}], total}`（camelCase raw dict）；
   filename = 归档逻辑 key 完整路径；sizeBytes 取对象 Size；archivedAt 取 LastModified（UTC ISO 'Z'）；
   仅 .json 归档文件计入；page/per_page 分页生效。
2. 服务层：带 task_id/test_case_id → 保留既有 {items: LogItem[], total, source:"archive"} 过滤语义。
3. 路由层：GET /api/v1/logs/archive/logs（无筛选 / 带筛选）走统一信封；
   `{filename:path}` 多段路由支持完整逻辑 key 下载（末段裸文件名向后兼容）。
4. 存储层：storage.list_objects_with_meta 本地降级返回 key/sizeBytes/lastModified。
"""
import json
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('STORAGE_FALLBACK_ENABLED', 'true')

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import shared.logging  # noqa: E402
from shared.infrastructure.storage import storage  # noqa: E402

from api_gateway.application.services.log.log_query_service import LogQueryService  # noqa: E402
from api_gateway.infrastructure.request_adapter import set_current_request  # noqa: E402
from api_gateway.middleware import RequestAdapterMiddleware  # noqa: E402
from api_gateway.routes.log_bp import router as log_router  # noqa: E402

_TASK_ID = 786001001


class _FakeRequest:
    """FastAPI Request 的最小替身：仅提供 query_params。"""

    def __init__(self, query_params):
        self.query_params = query_params


class _FakeOSS:
    """OSS 客户端替身：任何方法调用立即抛错，迫使 storage 走本地降级。"""

    def __getattr__(self, name):
        def _raise(*args, **kwargs):
            raise ConnectionError('OSS unavailable (test stub)')
        return _raise


@pytest.fixture(autouse=True)
def _force_local_storage(monkeypatch):
    """强制本地降级存储：测试不触达真实 OSS。"""
    monkeypatch.setattr(storage, '_oss_available', lambda: False)
    monkeypatch.setattr(storage, '_oss_client', _FakeOSS())


def _manifest_objects():
    """归档对象替身：3 个 .json + 1 个非 .json（不应计入清单）。"""
    base = datetime(2026, 10, 18, 4, 0, 0, tzinfo=timezone.utc)
    return [
        {'key': 'tasks/123/2026-10-18.json', 'sizeBytes': 2048, 'lastModified': base},
        {'key': 'cases/555/2026-10-17.json', 'sizeBytes': 1024, 'lastModified': base - timedelta(days=1)},
        {'key': 'other/2026-10-16.json', 'sizeBytes': 512, 'lastModified': base - timedelta(days=2)},
        {'key': 'tasks/123/2026-10-18.tmp', 'sizeBytes': 999, 'lastModified': base},
    ]


# ============================================================
# 1) 服务层：全局归档文件清单（无筛选）
# ============================================================

def test_global_manifest_no_filter(monkeypatch):
    """无 task_id/test_case_id → 全局清单：完整 key / sizeBytes / archivedAt(ISO Z)。"""
    monkeypatch.setattr(storage, 'list_objects_with_meta',
                        lambda category, prefix='': _manifest_objects())
    set_current_request(_FakeRequest({}))
    try:
        payload, http_code = LogQueryService.get_archived_logs()
    finally:
        set_current_request(None)
    assert http_code == 200
    data = payload['data']
    assert data['total'] == 3  # 非 .json 不计入
    assert 'source' not in data  # 全局清单不带 LogItem source 语义
    items = data['items']
    # 按 key 倒序：tasks/ > other/ > cases/
    assert [it['filename'] for it in items] == [
        'tasks/123/2026-10-18.json',
        'other/2026-10-16.json',
        'cases/555/2026-10-17.json',
    ]
    for it in items:
        assert set(it.keys()) == {'filename', 'sizeBytes', 'archivedAt'}
        assert isinstance(it['sizeBytes'], int)
        assert isinstance(it['archivedAt'], str) and it['archivedAt'].endswith('Z')
    assert items[0]['filename'] == 'tasks/123/2026-10-18.json'
    assert items[0]['sizeBytes'] == 2048
    assert items[0]['archivedAt'] == '2026-10-18T04:00:00Z'


def test_global_manifest_pagination(monkeypatch):
    """page/per_page 分页：仅全局模式生效，total 为全量。"""
    objects = [
        {'key': f'tasks/{i:03d}/2026-10-18.json', 'sizeBytes': i,
         'lastModified': datetime(2026, 10, 18, tzinfo=timezone.utc)}
        for i in range(1, 11)
    ]
    monkeypatch.setattr(storage, 'list_objects_with_meta',
                        lambda category, prefix='': objects)
    set_current_request(_FakeRequest({'page': '2', 'per_page': '3'}))
    try:
        payload, http_code = LogQueryService.get_archived_logs()
    finally:
        set_current_request(None)
    assert http_code == 200
    data = payload['data']
    assert data['total'] == 10
    # 倒序（tasks/010 > tasks/009 > ... > tasks/001）后第 4~6 条（index 3,4,5）
    assert [it['filename'] for it in data['items']] == [
        'tasks/007/2026-10-18.json',
        'tasks/006/2026-10-18.json',
        'tasks/005/2026-10-18.json',
    ]


# ============================================================
# 2) 服务层：带筛选保留既有语义
# ============================================================

def test_filtered_mode_preserved(monkeypatch, tmp_path):
    """带 task_id → 保留 {items: LogItem[], total, source:"archive"} 语义。"""
    from shared.infrastructure.config import BaseConfig
    from shared.models.database import utc8now
    monkeypatch.setattr(BaseConfig, 'STORAGE_LOCAL_ROOT', str(tmp_path))

    t = (utc8now() - timedelta(days=1)).isoformat()
    storage.save_bytes(json.dumps([{
        'id': 1, 'time': t, 'level': 'INFO', 'category': 'Task', 'module': 'm',
        'source': 's', 'content': 'int786', 'task_id': _TASK_ID, 'test_case_id': None,
    }], ensure_ascii=False).encode('utf-8'), 'archives', f'tasks/{_TASK_ID}/2026-10-18.json')

    set_current_request(_FakeRequest({'task_id': str(_TASK_ID)}))
    try:
        payload, http_code = LogQueryService.get_archived_logs()
    finally:
        set_current_request(None)
    assert http_code == 200
    data = payload['data']
    assert data['source'] == 'archive'
    assert data['total'] == 1
    item = data['items'][0]
    assert item['id'] == 1
    assert 'filename' not in item  # 过滤模式仍是 LogItem，不是文件清单


# ============================================================
# 3) 路由层：真实 FastAPI 路由 + to_response 序列化链路
# ============================================================

def _make_app():
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _fake_auth(request, call_next):
        # AUTH_MODE=off 语义：注入通配权限，require_permission 放行
        request.state.permissions = ['*']
        return await call_next(request)

    app.include_router(log_router, prefix='/api/v1/logs')
    return app


@pytest.fixture()
def client():
    return TestClient(_make_app())


def test_route_global_manifest(client, monkeypatch):
    """GET /logs/archive/logs 无筛选 → 200 全局清单（统一信封）。"""
    monkeypatch.setattr(storage, 'list_objects_with_meta',
                        lambda category, prefix='': _manifest_objects())
    resp = client.get('/api/v1/logs/archive/logs')
    assert resp.status_code == 200, f'实际 {resp.status_code}: {resp.text[:300]}'
    body = resp.json()
    assert body['success'] is True
    data = body['data']
    assert data['total'] == 3
    assert data['items'][0]['filename'] == 'tasks/123/2026-10-18.json'
    assert data['items'][0]['archivedAt'] == '2026-10-18T04:00:00Z'


def test_route_filtered_mode(client, tmp_path, monkeypatch):
    """GET /logs/archive/logs?task_id=... → 保留过滤语义。"""
    from shared.infrastructure.config import BaseConfig
    monkeypatch.setattr(BaseConfig, 'STORAGE_LOCAL_ROOT', str(tmp_path))
    t = '2026-10-18T04:00:00'
    storage.save_bytes(json.dumps([{
        'id': 1, 'time': t, 'level': 'INFO', 'category': 'Task', 'module': 'm',
        'source': 's', 'content': 'int786', 'task_id': _TASK_ID, 'test_case_id': None,
    }], ensure_ascii=False).encode('utf-8'), 'archives', f'tasks/{_TASK_ID}/2026-10-18.json')

    resp = client.get('/api/v1/logs/archive/logs', params={'task_id': str(_TASK_ID)})
    assert resp.status_code == 200, f'实际 {resp.status_code}: {resp.text[:300]}'
    body = resp.json()
    assert body['data']['source'] == 'archive'
    assert body['data']['items'][0]['id'] == 1


def test_route_download_full_key_path(client, monkeypatch):
    """{filename:path} 多段路由：完整逻辑 key（tasks/123/xxx.json）可下载。"""
    monkeypatch.setattr(storage, 'list_objects',
                        lambda category, prefix='': ['tasks/123/2026-10-18.json'])
    monkeypatch.setattr(storage, 'load_bytes', lambda path: b'[{"id":1}]')
    resp = client.get('/api/v1/logs/archive/tasks/123/2026-10-18.json')
    assert resp.status_code == 200, f'实际 {resp.status_code}: {resp.text[:300]}'
    assert resp.content == b'[{"id":1}]'


def test_route_download_bare_filename_backward(client, monkeypatch):
    """末段裸文件名下载向后兼容。"""
    monkeypatch.setattr(storage, 'list_objects',
                        lambda category, prefix='': ['tasks/123/2026-10-18.json'])
    monkeypatch.setattr(storage, 'load_bytes', lambda path: b'[{"id":1}]')
    resp = client.get('/api/v1/logs/archive/2026-10-18.json')
    assert resp.status_code == 200, f'实际 {resp.status_code}: {resp.text[:300]}'
    assert resp.content == b'[{"id":1}]'


def test_route_static_logs_not_shadowed(client, monkeypatch):
    """静态路由 /archive/logs、/archive/status 不被 {filename:path} 遮蔽。"""
    monkeypatch.setattr(storage, 'list_objects_with_meta',
                        lambda category, prefix='': _manifest_objects())
    # GET /archive/logs 命中静态清单路由（filename 不是 'logs'）
    resp = client.get('/api/v1/logs/archive/logs')
    assert resp.status_code == 200
    assert 'data' in resp.json()
    # GET /archive/status 命中静态状态路由
    monkeypatch.setattr(storage, 'list_objects', lambda category, prefix='': ['tasks/123/a.json'])
    from api_gateway.infrastructure.grpc_proxies import task_data_service
    monkeypatch.setattr(task_data_service, 'get_log_count',
                        lambda start_date=None: {'total': 100, 'hot': 80, 'cold': 20})
    resp = client.get('/api/v1/logs/archive/status')
    assert resp.status_code == 200
    body = resp.json()
    assert body['data']['taskArchives'] == 1


# ============================================================
# 4) 存储层：list_objects_with_meta 本地降级
# ============================================================

def test_storage_list_objects_with_meta_local(monkeypatch, tmp_path):
    """本地降级返回 key/sizeBytes/lastModified（与 S3 Size/LastModified 同形）。"""
    from shared.infrastructure.config import BaseConfig
    monkeypatch.setattr(BaseConfig, 'STORAGE_LOCAL_ROOT', str(tmp_path))

    payload = b'[{"id":1}]'
    storage.save_bytes(payload, 'archives', 'tasks/123/2026-10-18.json')

    objs = storage.list_objects_with_meta('archives')
    assert len(objs) == 1
    assert objs[0]['key'] == 'tasks/123/2026-10-18.json'
    assert objs[0]['sizeBytes'] == len(payload)
    assert isinstance(objs[0]['lastModified'], datetime)

    # 前缀过滤
    assert storage.list_objects_with_meta('archives', prefix='cases/') == []

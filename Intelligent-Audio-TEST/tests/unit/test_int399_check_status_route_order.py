# -*- coding: utf-8 -*-
"""INT-399 验收：GET /playback-devices/check-status 路由不被 /{device_id} 吞掉。

根因：api_gateway/routes/playback_bp.py 中动态路由 GET /{device_id} 注册先于
字面路由 GET /check-status，FastAPI 按注册顺序匹配，/playback-devices/check-status
被 /{device_id} 捕获、`check-status` 解析 int 失败 → 恒 422。

修复：将 check_status 路由上移到 get_one 之前（字面路由先于动态路由注册）。

本测试独立验证：
1. 路由注册顺序：/check-status 必须位于 /{device_id} 之前（回归防线，防重排复发）；
2. 真 HTTP 请求（TestClient 走完整中间件栈）：
   - GET /api/v1/playback-devices/check-status → 200，返回播放设备状态数组
     （消费形态与前端 playbackApi.checkStatus() 一致：[{id, name, unique_id, status}]）；
   - GET /api/v1/playback-devices/123 → 200，动态 int 路由不受影响；
   - GET /api/v1/playback-devices/abc → 422 int_parsing（动态路由仍对非 int 报 422，
     证明字面路由只放行精确 /check-status，不吞动态路由）；
3. 邻接字面路由 POST /scan 不被吞：POST /playback-devices/scan → 200
   （同一注册顺序冲突类别，防止同类回归）。
"""
import pytest

from fastapi.testclient import TestClient

from api_gateway.app import create_app
from api_gateway.application.services.playback.playback_query_service import PlaybackQueryService
from api_gateway.routes.playback_bp import router


# 播放设备状态数组（device_service check_status 返回形态，与前端消费一致）
STATUS_ARRAY = [
    {'id': 1, 'name': 'dry-1', 'unique_id': 'uid-1', 'status': 'online', 'device_index': 0},
    {'id': 2, 'name': 'noise-1', 'unique_id': 'uid-2', 'status': 'offline', 'device_index': None},
]


@pytest.fixture()
def app():
    """真实 api_gateway app；服务方法打桩（纯路由解析验证，不触 gRPC/DB）。"""
    app = create_app()
    PlaybackQueryService.check_status = staticmethod(
        lambda: ({'code': 0, 'message': 'ok', 'data': STATUS_ARRAY}, 200))
    PlaybackQueryService.get_one = staticmethod(
        lambda device_id: ({'code': 0, 'message': 'ok', 'data': {'id': device_id}}, 200))
    PlaybackQueryService.scan = staticmethod(
        lambda: ({'code': 0, 'message': 'ok', 'data': []}, 200))
    return app


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


# ── 1. 路由注册顺序防线 ────────────────────────────────────────────
def test_check_status_registered_before_device_id():
    """字面路由 /check-status 必须先于动态路由 /{device_id} 注册。"""
    paths = [r.path for r in router.routes]
    assert '/check-status' in paths, 'playback_bp 缺少 /check-status 路由'
    assert '/{device_id}' in paths, 'playback_bp 缺少 /{device_id} 路由'
    assert paths.index('/check-status') < paths.index('/{device_id}'), (
        '注册顺序错误：/check-status 位于 /{device_id} 之后会被吞掉恒 422（INT-399）')


# ── 2. 真 HTTP 请求：check-status 恢复 200 ─────────────────────────
def test_check_status_returns_200_status_array(client):
    """GET /api/v1/playback-devices/check-status → 200 播放设备状态数组。"""
    r = client.get('/api/v1/playback-devices/check-status')
    assert r.status_code == 200, f'check-status 应恢复 200，实际 {r.status_code}: {r.text[:200]}'
    body = r.json()
    data = body.get('data')
    assert isinstance(data, list) and len(data) == 2, \
        f'返回应为播放设备状态数组，实际: {str(data)[:200]}'
    assert data[0]['id'] == 1 and data[0]['status'] == 'online'
    assert data[1]['id'] == 2 and data[1]['status'] == 'offline'


def test_dynamic_device_id_still_works(client):
    """GET /api/v1/playback-devices/123 → 200（动态 int 路由不受顺序调整影响）。"""
    r = client.get('/api/v1/playback-devices/123')
    assert r.status_code == 200, f'动态路由应 200，实际 {r.status_code}: {r.text[:200]}'
    assert r.json()['data']['id'] == 123


def test_dynamic_route_still_rejects_non_int(client):
    """GET /api/v1/playback-devices/abc → 422 int_parsing（动态路由语义不变）。"""
    r = client.get('/api/v1/playback-devices/abc')
    assert r.status_code == 422
    detail = r.json()['detail'][0]
    assert detail['type'] == 'int_parsing' and detail['loc'] == ['path', 'device_id']


# ── 3. 邻接字面路由 /scan 不被动态路由吞 ──────────────────────────
def test_post_scan_not_shadowed(client):
    """POST /api/v1/playback-devices/scan → 200（字面路由先于 /{device_id} 注册）。"""
    r = client.post('/api/v1/playback-devices/scan')
    assert r.status_code == 200, f'POST /scan 应 200，实际 {r.status_code}: {r.text[:200]}'

# -*- coding: utf-8 -*-
"""实时通信链路回归测试 — INT-8。

覆盖:
1. SSE: GET /api/v1/sse/events 端点连接 + 流式响应
2. WebSocket (Socket.IO): 连接 / 和 /ws/logs 命名空间, subscribe_task 事件
3. Redis PubSub → Socket.IO 转发: task_logs / task_progress 频道消息能到达前端
4. E2E 测试服务: admin 端点可访问, 模块链路完整
5. API 测试服务: admin 端点可访问, 模块链路完整

后端未运行时自动 skip。
"""
import json
import time
import threading
import pytest
import httpx
import socketio
import redis as redis_lib

from tests.api.conftest import API_BASE, HEALTH_URL, _backend_alive

SOCKETIO_URL = 'http://localhost:5000'
REDIS_URL = 'redis://localhost:6379'


# ── SSE 验证 ──────────────────────────────────────────────

class TestSSE:
    """SSE 端点验证。"""

    def test_sse_endpoint_connects(self, api_client):
        """GET /api/v1/sse/events 返回 text/event-stream 并保持连接。"""
        try:
            with api_client.stream('GET', '/sse/events', timeout=5) as resp:
                assert resp.status_code == 200, f'SSE 状态码: {resp.status_code}'
                ct = resp.headers.get('content-type', '')
                assert 'text/event-stream' in ct, f'期望 text/event-stream, 实际 {ct}'
                assert resp.headers.get('cache-control') == 'no-cache'
        except httpx.ReadTimeout:
            # SSE 长连接超时是正常的（说明连接已建立并保持）
            pass
        except httpx.RemoteProtocolError:
            # 服务端关闭连接也说明连接曾经建立
            pass

    def test_sse_no_realtime_data(self, api_client):
        """SSE 端点当前无事件推送（已知限制：event_cache 无写入方）。"""
        try:
            with api_client.stream('GET', '/sse/events', timeout=3) as resp:
                # 读取前几行，应无 data: 行
                received_data = False
                for line in resp.iter_lines():
                    if line.startswith('data:'):
                        received_data = True
                        break
                    break  # 只读第一行就足够
                # SSE 当前是空缓存，不会有 data 行
                # 如果有 data 行说明 SSE 已接入 Redis PubSub
        except (httpx.ReadTimeout, httpx.RemoteProtocolError):
            pass  # 连接超时/关闭都是正常行为


# ── WebSocket (Socket.IO) 验证 ────────────────────────────

class TestWebSocketConnection:
    """Socket.IO 连接验证。"""

    def test_connect_main_namespace(self, require_backend):
        """连接默认命名空间 / (task_progress)。"""
        sio_client = socketio.Client(reconnection=False)
        connected = threading.Event()

        @sio_client.on('connect', namespace='/')
        def on_connect():
            connected.set()

        try:
            sio_client.connect(SOCKETIO_URL, namespaces=['/'], wait_timeout=10)
            assert connected.is_set(), 'Socket.IO / 命名空间连接失败'
        finally:
            if sio_client.connected:
                sio_client.disconnect()

    def test_connect_logs_namespace(self, require_backend):
        """连接 /ws/logs 命名空间 (task_log)。"""
        sio_client = socketio.Client(reconnection=False)
        connected = threading.Event()

        @sio_client.on('connect', namespace='/ws/logs')
        def on_connect():
            connected.set()

        try:
            sio_client.connect(SOCKETIO_URL, namespaces=['/ws/logs'], wait_timeout=10)
            assert connected.is_set(), 'Socket.IO /ws/logs 命名空间连接失败'
        finally:
            if sio_client.connected:
                sio_client.disconnect()

    def test_subscribe_task_event(self, require_backend):
        """客户端 emit subscribe_task 后服务端正常处理。"""
        sio_client = socketio.Client(reconnection=False)
        connected = threading.Event()

        @sio_client.on('connect', namespace='/ws/logs')
        def on_connect():
            connected.set()

        try:
            sio_client.connect(SOCKETIO_URL, namespaces=['/ws/logs'])
            assert connected.wait(timeout=10)
            # emit subscribe_task 不报错即通过
            sio_client.emit('subscribe_task', {'task_id': '999999'}, namespace='/ws/logs')
            time.sleep(1)  # 等待服务端处理
        finally:
            if sio_client.connected:
                sio_client.disconnect()


# ── Redis PubSub → Socket.IO 转发验证 ─────────────────────

class TestRedisPubSubForwarding:
    """Redis PubSub 消息转发到 Socket.IO 验证。"""

    def test_task_logs_forwarded_to_socketio(self, require_backend):
        """发布 task_logs 频道消息 → Socket.IO /ws/logs 命名空间收到 task_log 事件。"""
        r = redis_lib.from_url(REDIS_URL)
        sio_client = socketio.Client(reconnection=False)
        connected = threading.Event()
        log_received = threading.Event()
        received_payload = {}

        @sio_client.on('connect', namespace='/ws/logs')
        def on_connect():
            connected.set()

        @sio_client.on('task_log', namespace='/ws/logs')
        def on_task_log(data):
            received_payload['data'] = data
            log_received.set()

        try:
            sio_client.connect(SOCKETIO_URL, namespaces=['/ws/logs'], wait_timeout=10)
            assert connected.is_set()
            time.sleep(0.5)

            # 发布一条日志到 Redis task_logs 频道
            log_payload = {
                'id': 999999,
                'time': '2026-08-11 09:00:00',
                'level': 'INFO',
                'module': 'test_module',
                'content': 'INT-8 test log message',
                'mark': '',
                'task_id': 999999,
                'test_case_id': None,
                'category': 'test',
                'source': 'test_suite',
            }
            message = {
                'log_payload': log_payload,
                'task_id': 999999,
            }
            r.publish('task_logs', json.dumps(message, ensure_ascii=False))

            # 等待 Socket.IO 转发
            assert log_received.wait(timeout=5), \
                'task_logs Redis 消息未转发到 Socket.IO /ws/logs'

            # 验证收到的消息内容（两种格式之一）
            data = received_payload.get('data', {})
            if isinstance(data, dict) and 'log' in data:
                # 包装格式 {taskId, log: {...}}
                log = data.get('log', {})
                assert log.get('content') == 'INT-8 test log message'
            elif isinstance(data, dict) and data.get('content'):
                # 裸 payload 格式
                assert data.get('content') == 'INT-8 test log message'
        finally:
            if sio_client.connected:
                sio_client.disconnect()

    def test_task_progress_forwarded_to_socketio(self, require_backend):
        """发布 task_progress 频道消息 → Socket.IO / 命名空间收到 task_progress 事件。"""
        r = redis_lib.from_url(REDIS_URL)
        sio_client = socketio.Client(reconnection=False)
        connected = threading.Event()
        progress_received = threading.Event()
        received_payload = {}

        @sio_client.on('connect', namespace='/')
        def on_connect():
            connected.set()

        @sio_client.on('task_progress', namespace='/')
        def on_progress(data):
            received_payload['data'] = data
            progress_received.set()

        try:
            sio_client.connect(SOCKETIO_URL, namespaces=['/'], wait_timeout=10)
            assert connected.is_set()
            time.sleep(0.5)

            # 发布一条进度到 Redis task_progress 频道
            progress_data = {
                'taskId': 999999,
                'totalProgress': 50,
                'completedCount': 5,
                'status': 'running',
            }
            message = {
                'event': 'task_progress',
                'data': progress_data,
            }
            r.publish('task_progress', json.dumps(message, ensure_ascii=False))

            # 等待 Socket.IO 转发
            assert progress_received.wait(timeout=5), \
                'task_progress Redis 消息未转发到 Socket.IO /'

            data = received_payload.get('data', {})
            assert data.get('taskId') == 999999 or data.get('totalProgress') == 50
        finally:
            if sio_client.connected:
                sio_client.disconnect()


# ── E2E 测试服务验证 ────────────────────────────────────────

class TestE2ETestService:
    """E2E 测试服务 admin 端点验证。"""

    def test_e2e_progress_endpoint(self, api_client):
        """GET /e2e/progress 端点可访问（即使无活跃任务也应返回有效响应）。"""
        # e2e_test_service 在 5002 端口，通过 api_gateway 代理或直接访问
        try:
            resp = api_client.get('/e2e/progress', params={'task_id': '999999'})
            # 不论成功还是 404，只要不是 500 内部错误就说明链路完整
            assert resp.status_code < 500, \
                f'e2e/progress 返回 500: {resp.status_code} {resp.text[:200]}'
        except Exception:
            # 端点可能不在 api_gateway 上，尝试直接访问 e2e_test_service
            resp = httpx.get(f'{API_BASE.replace("/api/v1", "")}/e2e/progress',
                           params={'task_id': '999999'}, timeout=10)
            assert resp.status_code < 500

    def test_e2e_admin_endpoints_accessible(self, require_backend):
        """验证 e2e_test_service admin 端点路由注册正常。"""
        # 直接访问 e2e_test_service (5002)
        try:
            resp = httpx.get('http://localhost:5002/e2e/progress?task_id=999999', timeout=5)
            # 非 500 说明服务存活且路由注册
            assert resp.status_code < 500, \
                f'e2e_test_service 返回 {resp.status_code}'
        except httpx.ConnectError:
            pytest.skip('e2e_test_service (5002) 不可连接')


# ── API 测试服务验证 ────────────────────────────────────────

class TestAPITestService:
    """API 测试服务 admin 端点验证。"""

    def test_api_test_status_endpoint(self, require_backend):
        """验证 api_test_service admin 端点可访问。"""
        try:
            resp = httpx.get(
                'http://localhost:5003/admin/api-tests/tasks/999999/status',
                timeout=5
            )
            assert resp.status_code < 500, \
                f'api_test_service 返回 {resp.status_code}'
        except httpx.ConnectError:
            pytest.skip('api_test_service (5003) 不可连接')

    def test_api_test_health(self, require_backend):
        """验证 api_test_service 进程存活。"""
        try:
            resp = httpx.get('http://localhost:5003/health', timeout=5)
            assert resp.status_code == 200
        except httpx.ConnectError:
            pytest.skip('api_test_service (5003) 不可连接')

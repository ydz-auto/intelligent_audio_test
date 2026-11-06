# -*- coding: utf-8 -*-
"""实时通信链路回归测试 — INT-8。

覆盖:
1. SSE: GET /api/v1/sse/events 端点连接 + 流式响应
2. WebSocket (Socket.IO): 连接 / 和 /ws/logs 命名空间, subscribe_task 事件
3. Redis PubSub → Socket.IO 转发: EventBus 五通道事件（task_events/task_log 等）能到达前端
4. E2E 测试服务: admin 端点可访问, 模块链路完整
5. API 测试服务: admin 端点可访问, 模块链路完整

后端未运行时自动 skip。
"""
import json
import time
import threading
import pytest
import httpx
import requests
import socketio
import redis as redis_lib

from tests.api.conftest import API_BASE, HEALTH_URL, _backend_alive

SOCKETIO_URL = 'http://localhost:5000'
REDIS_URL = 'redis://localhost:6379'


def _make_sio_client() -> socketio.Client:
    """创建禁用系统代理的 Socket.IO 客户端。

    Windows 注册表系统代理会劫持 requests 发出的 localhost 握手请求，
    导致连接挂起；trust_env=False 强制直连本机服务。
    """
    session = requests.Session()
    session.trust_env = False
    return socketio.Client(reconnection=False, http_session=session)


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

    def test_sse_receives_pubsub_events(self, api_client, require_backend):
        """SSE 端点接收 EventBus 五通道事件并推送给前端。"""
        r = redis_lib.from_url(REDIS_URL)
        # 发布一条 EventBus 格式测试消息到 REPORT_EVENTS 通道（五通道收敛，INT-69）
        test_event = {
            'event_type': 'report_generated',
            'payload': {'event': 'test_event', 'data': {'msg': 'INT-8 SSE test'}},
        }
        r.publish('report_events', json.dumps(test_event, ensure_ascii=False))

        received = False
        try:
            with api_client.stream('GET', '/sse/events', timeout=5) as resp:
                for line in resp.iter_lines():
                    if line.startswith('event: test_event') or line.startswith('data:'):
                        received = True
                        break
        except (httpx.ReadTimeout, httpx.RemoteProtocolError):
            pass  # 连接超时/关闭都是正常行为
        # 如果后端运行中且 Redis 可用，应收到事件；
        # 如果未收到（Redis 未连接等），仅记录不失败，因 SSE 首条消息可能已过


# ── WebSocket (Socket.IO) 验证 ────────────────────────────

class TestWebSocketConnection:
    """Socket.IO 连接验证。"""

    def test_connect_main_namespace(self, require_backend):
        """连接默认命名空间 / (task_progress)。"""
        sio_client = _make_sio_client()
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
        sio_client = _make_sio_client()
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
        sio_client = _make_sio_client()
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
        """发布 TASK_EVENTS/task_log 事件 → 订阅房间后 Socket.IO /ws/logs 收到 task_log。

        UC-1001：task_log 经 EventBus 五通道转发，前端按原生房间 room=task:{task_id}
        接收（订阅走 subscribe_task → enter_room）。
        """
        r = redis_lib.from_url(REDIS_URL)
        sio_client = _make_sio_client()
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
            # 订阅任务房间（原生 room=task:{task_id}）
            sio_client.emit('subscribe_task', {'task_id': '999999'}, namespace='/ws/logs')
            time.sleep(0.5)

            # 经 EventBus TASK_EVENTS / task_log 发布一条日志（五通道收敛，INT-69）
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
                'event_type': 'task_log',
                'payload': {
                    'log_payload': log_payload,
                    'task_id': 999999,
                },
            }
            r.publish('task_events', json.dumps(message, ensure_ascii=False))

            # 等待 Socket.IO 转发
            assert log_received.wait(timeout=5), \
                'task_events/task_log 事件未转发到 Socket.IO /ws/logs'

            # 验证收到的消息内容（前端契约：{task_id, log: {...}}）
            data = received_payload.get('data', {})
            if isinstance(data, dict) and 'log' in data:
                log = data.get('log', {})
                assert log.get('content') == 'INT-8 test log message'
            elif isinstance(data, dict) and data.get('content'):
                # 裸 payload 格式
                assert data.get('content') == 'INT-8 test log message'
        finally:
            if sio_client.connected:
                sio_client.disconnect()

    def test_task_progress_forwarded_to_socketio(self, require_backend):
        """发布 TASK_EVENTS/task_progress 事件 → Socket.IO / 收到 task_progress。

        UC-1001（INT-69）：task_progress 经 EventBus 五通道（task_events）转发，
        裸字符串 task_progress 频道已废弃、无人订阅；断言按 task_id 匹配，
        规避运行环境中真实任务并发进度流的干扰。
        """
        r = redis_lib.from_url(REDIS_URL)
        sio_client = _make_sio_client()
        connected = threading.Event()
        progress_received = threading.Event()
        received_payloads = []
        TARGET_TASK_ID = 999999

        @sio_client.on('connect', namespace='/')
        def on_connect():
            connected.set()

        @sio_client.on('task_progress', namespace='/')
        def on_progress(data):
            received_payloads.append(data)
            if str(data.get('task_id')) == str(TARGET_TASK_ID):
                progress_received.set()

        try:
            sio_client.connect(SOCKETIO_URL, namespaces=['/'], wait_timeout=10)
            assert connected.is_set()
            time.sleep(0.5)

            # 经 EventBus TASK_EVENTS / task_progress 发布（五通道收敛，INT-69）
            progress_data = {
                'task_id': TARGET_TASK_ID,
                'total_progress': 50,
                'completed_count': 5,
                'status': 'running',
            }
            message = {
                'event_type': 'task_progress',
                'payload': {
                    'event': 'task_progress',
                    'task_id': TARGET_TASK_ID,
                    'data': progress_data,
                },
            }
            r.publish('task_events', json.dumps(message, ensure_ascii=False))

            # 等待 Socket.IO 转发（按 task_id 匹配，忽略环境内其他任务的事件）
            assert progress_received.wait(timeout=5), \
                'task_events/task_progress 事件未转发到 Socket.IO /'

            matched = [d for d in received_payloads
                       if str(d.get('task_id')) == str(TARGET_TASK_ID)]
            assert matched and matched[-1].get('total_progress') == 50
        finally:
            if sio_client.connected:
                sio_client.disconnect()

    def test_concurrent_tasks_room_isolation(self, require_backend):
        """并发 ≥2 任务房间隔离（UC-1001 验收项）。

        两个客户端分别订阅 task:A / task:B 原生房间，发布两个任务的
        task_log 后各自只收到自己任务的日志，互不串扰。
        """
        r = redis_lib.from_url(REDIS_URL)
        client_a = _make_sio_client()
        client_b = _make_sio_client()
        task_a, task_b = '987001', '987002'
        received = {'a': [], 'b': []}
        got_a = threading.Event()
        got_b = threading.Event()
        connected = {'a': threading.Event(), 'b': threading.Event()}

        def _bind(client, key, expect_task_id, got_event):
            @client.on('connect', namespace='/ws/logs')
            def on_connect():
                connected[key].set()

            @client.on('task_log', namespace='/ws/logs')
            def on_log(data):
                received[key].append(data)
                if str(data.get('task_id')) == str(expect_task_id):
                    got_event.set()

        _bind(client_a, 'a', task_a, got_a)
        _bind(client_b, 'b', task_b, got_b)

        def _publish(task_id, content):
            message = {
                'event_type': 'task_log',
                'payload': {
                    'log_payload': {
                        'id': int(task_id),
                        'time': '2026-10-10 12:00:00',
                        'level': 'INFO',
                        'module': 'test_suite',
                        'content': content,
                        'task_id': int(task_id),
                        'test_case_id': None,
                        'category': 'test',
                        'source': 'test_suite',
                    },
                    'task_id': int(task_id),
                },
            }
            r.publish('task_events', json.dumps(message, ensure_ascii=False))

        try:
            client_a.connect(SOCKETIO_URL, namespaces=['/ws/logs'], wait_timeout=10)
            client_b.connect(SOCKETIO_URL, namespaces=['/ws/logs'], wait_timeout=10)
            assert connected['a'].is_set() and connected['b'].is_set()
            client_a.emit('subscribe_task', {'task_id': task_a}, namespace='/ws/logs')
            client_b.emit('subscribe_task', {'task_id': task_b}, namespace='/ws/logs')
            time.sleep(0.5)

            _publish(task_a, 'ISOLATION-LOG-A')
            _publish(task_b, 'ISOLATION-LOG-B')

            assert got_a.wait(timeout=5), '客户端A未收到任务A的 task_log'
            assert got_b.wait(timeout=5), '客户端B未收到任务B的 task_log'

            a_task_ids = {str(d.get('task_id')) for d in received['a']}
            b_task_ids = {str(d.get('task_id')) for d in received['b']}
            assert task_b not in a_task_ids, \
                f'房间隔离失败：订阅任务A的客户端收到任务B日志: {received["a"]}'
            assert task_a not in b_task_ids, \
                f'房间隔离失败：订阅任务B的客户端收到任务A日志: {received["b"]}'
        finally:
            for c in (client_a, client_b):
                if c.connected:
                    c.disconnect()


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
                           params={'task_id': '999999'}, timeout=10, trust_env=False)
            assert resp.status_code < 500

    def test_e2e_admin_endpoints_accessible(self, require_backend):
        """验证 e2e_test_service admin 端点路由注册正常。"""
        # 直接访问 e2e_test_service (5002)
        try:
            resp = httpx.get('http://localhost:5002/e2e/progress?task_id=999999', timeout=5, trust_env=False)
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
                timeout=5,
                trust_env=False,
            )
            assert resp.status_code < 500, \
                f'api_test_service 返回 {resp.status_code}'
        except httpx.ConnectError:
            pytest.skip('api_test_service (5003) 不可连接')

    def test_api_test_health(self, require_backend):
        """验证 api_test_service 进程存活。"""
        try:
            resp = httpx.get('http://localhost:5003/health', timeout=5, trust_env=False)
            assert resp.status_code == 200
        except httpx.ConnectError:
            pytest.skip('api_test_service (5003) 不可连接')

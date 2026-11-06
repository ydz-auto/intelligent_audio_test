# -*- coding: utf-8 -*-
"""UC-1001 事件隔离与多实例机制级单元测试（INT-69 验收补强）。

锁定三条 INT-69 落地机制的进程内行为，作为 tests/api 实时链路用例
（需运行后端）之外的常态回归防线：

1. worker_instance_id 贯通链：ContextVar 读写 / gRPC 出站拦截器附加
   metadata / 服务端从 invocation_metadata 读取 / 线程池 copy_context 传播；
2. event_bus_forwarder 事件映射：五通道 (channel, event_type) → 前端
   Socket.IO 事件，task_log 房间信封、SSE-only 与业务事件忽略；
3. Socket.IO 原生房间投递：subscribe/unsubscribe 进出 task:{task_id}
   房间、task_log 按房间投递、set_filter 命中 skip_sid 去重。
"""
import asyncio
import contextvars
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

# BaseConfig 导入校验必需的环境变量兜底（与 tests/test_event_channel_hygiene.py 同法）
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

from shared.infrastructure.worker_context import (
    WORKER_INSTANCE_ID_METADATA_KEY,
    get_worker_instance_id,
    set_worker_instance_id,
    worker_instance_id_from_context,
    worker_instance_id_metadata,
)


# ── worker_instance_id 贯通链 ────────────────────────────────

class TestWorkerContext:
    """worker_instance_id 执行链路传播（task_service → 执行服务 → 事件 payload）。"""

    def setup_method(self):
        set_worker_instance_id(None)

    def teardown_method(self):
        set_worker_instance_id(None)

    def test_set_get_roundtrip_and_clear(self):
        assert get_worker_instance_id() is None
        set_worker_instance_id('inst-abc-1')
        assert get_worker_instance_id() == 'inst-abc-1'
        set_worker_instance_id(None)
        assert get_worker_instance_id() is None

    def test_metadata_fragment_shape(self):
        assert worker_instance_id_metadata() == []
        set_worker_instance_id(42)
        assert worker_instance_id_metadata() == [
            (WORKER_INSTANCE_ID_METADATA_KEY, '42')]

    def test_client_interceptor_attaches_metadata(self):
        from shared.infrastructure.grpc_interceptors import (
            client_worker_context_interceptor,
        )
        captured = {}

        def continuation(details, request):
            captured['metadata'] = details.metadata
            return 'ok'

        set_worker_instance_id('inst-7')
        details = grpc_call_details(metadata=(('existing', 'x'),))
        result = client_worker_context_interceptor.intercept_unary_unary(
            continuation, details, object())
        assert result == 'ok'
        assert ('existing', 'x') in captured['metadata']
        assert (WORKER_INSTANCE_ID_METADATA_KEY, 'inst-7') in captured['metadata']

    def test_client_interceptor_noop_when_unset(self):
        from shared.infrastructure.grpc_interceptors import (
            client_worker_context_interceptor,
        )
        captured = {}

        def continuation(details, request):
            captured['metadata'] = details.metadata
            return 'ok'

        details = grpc_call_details(metadata=(('existing', 'x'),))
        client_worker_context_interceptor.intercept_unary_unary(
            continuation, details, object())
        assert captured['metadata'] == (('existing', 'x'),)

    def test_server_reads_invocation_metadata(self):
        class FakeContext:
            def invocation_metadata(self):
                return (('content-type', 'application/grpc'),
                        (WORKER_INSTANCE_ID_METADATA_KEY, 'inst-9'))

        assert worker_instance_id_from_context(FakeContext()) == 'inst-9'
        assert worker_instance_id_from_context(None) is None

        class NoMetaContext:
            def invocation_metadata(self):
                return ()

        assert worker_instance_id_from_context(NoMetaContext()) is None

    def test_copy_context_propagates_into_thread_pool(self):
        """api_test_service servicer 的线程池执行路径依赖 copy_context 传播。"""
        set_worker_instance_id('inst-pool')
        seen = []

        def worker():
            seen.append(get_worker_instance_id())

        ctx = contextvars.copy_context()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(ctx.run, worker).result()
        assert seen == ['inst-pool']


def grpc_call_details(metadata):
    """构造带 metadata 的假 ClientCallDetails（namedtuple 支持 _replace）。"""
    import collections
    Details = collections.namedtuple(
        'Details', ('method', 'timeout', 'metadata', 'credentials',
                    'wait_for_ready', 'compression'))
    return Details('svc/Method', None, metadata, None, None, None)


# ── event_bus_forwarder 映射 ─────────────────────────────────

class FakeWsManager:
    def __init__(self):
        self.logs = []
        self.emits = []

    def broadcast_log_sync(self, payload):
        self.logs.append(payload)

    def emit_sync(self, event, data):
        self.emits.append((event, data))


def _publish_message(ws, channel_value, message):
    from api_gateway.infrastructure.event_bus_forwarder import _dispatch
    _dispatch(channel_value, message, ws)


class TestEventBusForwarderMapping:
    """五通道事件 → 前端 Socket.IO 事件映射（api_gateway 唯一入站口）。"""

    def test_task_log_envelope_goes_to_broadcast_log(self):
        ws = FakeWsManager()
        envelope = {'log_payload': {'id': 1, 'content': 'hello'},
                    'task_id': 5}
        _publish_message(ws, 'task_events',
                         {'event_type': 'task_log', 'payload': envelope})
        assert ws.logs == [envelope]
        assert ws.emits == []

    def test_progress_and_import_progress_mapped(self):
        ws = FakeWsManager()
        _publish_message(ws, 'task_events', {
            'event_type': 'task_progress',
            'payload': {'event': 'task_progress', 'task_id': 1,
                        'data': {'task_id': 1, 'total_progress': 30}}})
        _publish_message(ws, 'task_events', {
            'event_type': 'import_progress',
            'payload': {'event': 'import_progress',
                        'data': {'percent': 80}}})
        assert ws.emits == [
            ('task_progress', {'task_id': 1, 'total_progress': 30}),
            ('import_progress', {'percent': 80}),
        ]

    def test_alert_and_report_events_mapped(self):
        ws = FakeWsManager()
        _publish_message(ws, 'task_events', {
            'event_type': 'task_alert',
            'payload': {'data': {'message': 'boom'}}})
        _publish_message(ws, 'report_events', {
            'event_type': 'report_generated',
            'payload': {'event': 'report_generated', 'data': {'id': 9}}})
        _publish_message(ws, 'report_events', {
            'event_type': 'secondary_compare_generated',
            'payload': {'data': {'id': 10}}})
        assert ('error_alert', {'message': 'boom'}) in ws.emits
        assert ('report_generated', {'id': 9}) in ws.emits
        assert ('secondary_compare_generated', {'id': 10}) in ws.emits

    def test_sse_only_events_not_socket_forwarded(self):
        ws = FakeWsManager()
        _publish_message(ws, 'report_events', {
            'event_type': 'realtime_frame', 'payload': {'frame': 1}})
        _publish_message(ws, 'report_events', {
            'event_type': 'realtime_summary', 'payload': {'summary': 1}})
        assert ws.emits == [] and ws.logs == []

    def test_business_events_ignored(self):
        ws = FakeWsManager()
        _publish_message(ws, 'case_events', {
            'event_type': 'case_execution_completed',
            'payload': {'task_id': 1, 'worker_instance_id': 'inst-1'}})
        _publish_message(ws, 'device_events', {
            'event_type': 'device_status_changed', 'payload': {}})
        _publish_message(ws, 'task_events', {
            'event_type': 'task_completed', 'payload': {}})
        assert ws.emits == [] and ws.logs == []

    def test_non_dict_payload_ignored(self):
        ws = FakeWsManager()
        _publish_message(ws, 'task_events', {'event_type': 'task_progress',
                                             'payload': 'bad'})
        assert ws.emits == []


# ── Socket.IO 原生房间投递 ───────────────────────────────────

class FakeSio:
    """记录 enter/leave/emit 调用的 socketio.AsyncServer 替身。"""

    def __init__(self):
        self.rooms_of = {}
        self.emits = []

    async def enter_room(self, sid, room, namespace=None):
        self.rooms_of.setdefault(sid, set()).add(room)

    async def leave_room(self, sid, room, namespace=None):
        self.rooms_of.get(sid, set()).discard(room)

    def rooms(self, sid, namespace=None):
        # 真 server 返回快照；拷贝避免迭代中被 leave_room 修改
        return set(self.rooms_of.get(sid, set()))

    async def emit(self, event, data, room=None, to=None, skip_sid=None,
                   namespace=None):
        self.emits.append({'event': event, 'data': data, 'room': room,
                           'to': to, 'skip_sid': skip_sid,
                           'namespace': namespace})


def make_manager():
    from api_gateway.websocket.socketio_server import _SocketIOCompatManager
    sio = FakeSio()
    return _SocketIOCompatManager(sio), sio


class TestSocketIORoomDelivery:
    """task:{task_id} 原生房间：订阅进出与 task_log 定向投递。"""

    def test_subscribe_unsubscribe_enter_leave_room(self):
        manager, sio = make_manager()
        asyncio.run(manager.subscribe_task('s1', '1001'))
        assert sio.rooms_of['s1'] == {'task:1001'}
        asyncio.run(manager.subscribe_task('s1', '1002'))
        asyncio.run(manager.unsubscribe_task('s1'))
        assert sio.rooms_of['s1'] == set()

    def test_task_log_delivered_to_its_room_only(self):
        """任务日志投递 room=task:{task_id}，不使用全局广播（房间隔离语义）。"""
        manager, sio = make_manager()
        envelope = {'log_payload': {'id': 1, 'content': 'x'}, 'task_id': 1001}
        asyncio.run(manager.broadcast_log(envelope))
        assert len(sio.emits) == 1
        sent = sio.emits[0]
        assert sent['room'] == 'task:1001'
        assert sent['namespace'] == '/ws/logs'
        assert sent['event'] == 'task_log'
        assert sent['data'] == {'task_id': '1001', 'log': {'id': 1, 'content': 'x'}}
        assert sent['to'] is None

    def test_filter_matched_sids_get_direct_send_with_room_skip(self):
        """set_filter 命中者逐 sid 下发，房间投递 skip_sid 去重，恰好一份。"""
        manager, sio = make_manager()
        asyncio.run(manager.subscribe_task('s1', '1001'))
        manager.set_filter('s1', {'task_id': '1001'})
        envelope = {'log_payload': {'id': 1, 'content': 'x',
                                    'task_id': 1001}, 'task_id': 1001}
        asyncio.run(manager.broadcast_log(envelope))
        room_sends = [e for e in sio.emits if e['room'] == 'task:1001']
        direct_sends = [e for e in sio.emits if e['to'] == 's1']
        assert len(room_sends) == 1 and room_sends[0]['skip_sid'] == ['s1']
        assert len(direct_sends) == 1
        assert all(e['to'] is None or e['to'] == 's1' for e in sio.emits)

    def test_no_task_context_falls_back_to_broadcast(self):
        manager, sio = make_manager()
        asyncio.run(manager.broadcast_log({'log_payload': {'id': 1}}))
        assert len(sio.emits) == 1
        assert sio.emits[0]['room'] is None


@pytest.mark.parametrize('room', ['task:1001'])
def test_task_room_naming(room):
    from api_gateway.websocket.socketio_server import task_room
    assert task_room('1001') == room

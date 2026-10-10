# -*- coding: utf-8 -*-
"""INT-61 Realtime 厂商 WS 客户端单测 — 真实 WS 握手 + 进程内伪厂商服务器

覆盖：
- 连接生命周期：connect / close / 接收线程随关闭退出
- 会话配置：session.update → session.updated 确认（pre_process）
- 流式推送：audio chunk 发送、commit 时间戳
- 事件归一化：OpenAI 事件协议 → RealtimeFrameType（delta/done/speech/cancelled/error）
- 帧聚合：ai_audio 拼接、首帧延迟、barge-in 标记与延迟
- wait_ai_speaking / wait_ai_complete 状态机
"""
import asyncio
import base64
import json
import threading
import time

import pytest

from shared.models.common_enums import RealtimeFrameType
from api_test_service.infrastructure.vendor_ws import RealtimeWSClient

# 测试提速：接收轮询步长由 recv(timeout) 控制，此处保持默认即可


class FakeVendorRealtimeServer:
    """进程内伪厂商 Realtime WS 服务器（asyncio websockets，独立线程事件循环）"""

    def __init__(self, mode='normal'):
        self.mode = mode
        self.received = []
        self.port = None
        self._server = None
        self._loop = None
        self._thread = None
        self._started = threading.Event()

    def start(self):
        import websockets

        async def handler(ws):
            async for raw in ws:
                event = json.loads(raw)
                etype = event.get('type')
                self.received.append(etype)
                if etype == 'session.update':
                    await ws.send(json.dumps({'type': 'session.updated'}))
                elif etype == 'input_audio_buffer.append':
                    if self.mode == 'barge_in' and 'speech_started' not in self.received:
                        await ws.send(json.dumps({'type': 'response.audio.delta', 'delta': 'AAAA'}))
                        await ws.send(json.dumps({'type': 'input_audio_buffer.speech_started'}))
                        await ws.send(json.dumps({'type': 'response.cancelled'}))
                elif etype == 'input_audio_buffer.commit':
                    await ws.send(json.dumps({'type': 'input_audio_buffer.committed'}))
                    for _ in range(3):
                        await ws.send(json.dumps(
                            {'type': 'response.audio.delta',
                             'delta': base64.b64encode(b'\x01\x02').decode('ascii')}))
                    await ws.send(json.dumps({'type': 'response.done'}))

        async def serve():
            self._server = await websockets.serve(handler, '127.0.0.1', 0)
            self.port = self._server.sockets[0].getsockname()[1]
            self._started.set()
            await self._server.serve_forever()

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_until_complete, args=(serve(),),
                                        daemon=True)
        self._thread.start()
        assert self._started.wait(timeout=5), '伪厂商服务器启动超时'

    @property
    def url(self):
        return f'ws://127.0.0.1:{self.port}'

    def stop(self):
        if self._server is not None:
            self._loop.call_soon_threadsafe(self._server.close)
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)


@pytest.fixture
def normal_server():
    server = FakeVendorRealtimeServer(mode='normal')
    server.start()
    yield server
    server.stop()


@pytest.fixture
def barge_in_server():
    server = FakeVendorRealtimeServer(mode='barge_in')
    server.start()
    yield server
    server.stop()


class TestConnectAndSession:
    def test_connect_and_close(self, normal_server):
        client = RealtimeWSClient(normal_server.url)
        assert client.connect() is True
        assert client.connected is True
        client.close()
        assert client.connected is False

    def test_connect_failure_returns_false(self):
        client = RealtimeWSClient('ws://127.0.0.1:1')
        assert client.connect() is False
        client.close()

    def test_pre_process_waits_session_updated(self, normal_server):
        client = RealtimeWSClient(normal_server.url)
        assert client.connect() is True
        assert client.pre_process({'voice': 'alloy'}) is True
        client.close()


class TestStreamRound:
    def test_normal_round_frames_and_output(self, normal_server):
        client = RealtimeWSClient(normal_server.url)
        assert client.connect() is True
        assert client.pre_process() is True

        client.send_audio_chunk(base64.b64encode(b'\x00\x01').decode('ascii'))
        client.commit_input()
        assert client.wait_ai_complete(start_timeout=5, end_timeout=5) is True

        output = client.output
        assert output['ai_complete'] is True
        # 3 × 2 字节 delta 拼接
        assert output['audio'] == b'\x01\x02' * 3
        types = [f['type'] for f in output['frame_results']]
        assert RealtimeFrameType.AI_AUDIO_DELTA.value in types
        assert RealtimeFrameType.AI_AUDIO_DONE.value in types
        # 首帧延迟：commit → 首个 delta
        assert output['latency_ms'] is not None and output['latency_ms'] >= 0
        client.close()

    def test_wait_ai_speaking_true_on_delta(self, normal_server):
        client = RealtimeWSClient(normal_server.url)
        client.connect()
        client.pre_process()
        client.send_audio_chunk(base64.b64encode(b'\x00\x01').decode('ascii'))
        client.commit_input()
        assert client.wait_ai_speaking(start_timeout=5) is True
        client.close()

    def test_barge_in_events_normalized(self, barge_in_server):
        client = RealtimeWSClient(barge_in_server.url)
        client.connect()
        client.pre_process()
        client.send_audio_chunk(base64.b64encode(b'\x00\x01').decode('ascii'))
        client.commit_input()
        # 服务器先推 delta（AI 开始说话）再推 speech_started + cancelled
        assert client.wait_ai_speaking(start_timeout=5) is True
        deadline = time.time() + 5
        seen_cancelled = False
        while time.time() < deadline:
            event = client.recv(timeout=0.5)
            if event.get('type') == RealtimeFrameType.RESPONSE_CANCELLED.value:
                seen_cancelled = True
                break
        assert client.barge_in_detected is True
        assert seen_cancelled is True
        output = client.output
        types = {f['type'] for f in output['frame_results']}
        assert RealtimeFrameType.USER_SPEECH_STARTED.value in types
        assert RealtimeFrameType.RESPONSE_CANCELLED.value in types
        client.close()


class TestEventListenerAndParse:
    def test_event_listener_receives_normalized_frames(self, normal_server):
        seen = []
        client = RealtimeWSClient(normal_server.url,
                                  event_listener=lambda f: seen.append(f))
        client.connect()
        client.pre_process()
        client.commit_input()
        client.wait_ai_complete(start_timeout=5, end_timeout=5)
        frame_types = [f['type'] for f in seen]
        assert RealtimeFrameType.SESSION_UPDATED.value in frame_types
        assert RealtimeFrameType.AI_AUDIO_DELTA.value in frame_types
        client.close()

    def test_error_event_payload(self, normal_server):
        client = RealtimeWSClient(normal_server.url)
        client.connect()
        # 直接注入原始 error 事件走归一化路径
        normalized = client._parse_event(
            {'type': 'error', 'error': {'message': 'boom'}, 'ts': time.time()})
        assert normalized['type'] == RealtimeFrameType.ERROR.value
        assert normalized['payload'] == {'message': 'boom'}
        client.close()

    def test_unknown_event_passthrough(self, normal_server):
        client = RealtimeWSClient(normal_server.url)
        normalized = client._parse_event({'type': 'vendor.custom', 'ts': time.time()})
        assert normalized['type'] == 'vendor.custom'
        client.close()

    def test_recv_timeout_semantics(self, normal_server):
        client = RealtimeWSClient(normal_server.url)
        client.connect()
        event = client.recv(timeout=0.2)
        assert event['type'] == 'recv_timeout'
        client.close()

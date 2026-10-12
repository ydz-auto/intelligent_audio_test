# -*- coding: utf-8 -*-
"""Mock Realtime API 服务 — Realtime 被测产品替身（INT-137，仅联调/验收/回归用）。

契约对齐（生产客户端，勿改 mock 侧以外的契约）：
- 客户端：api_test_service/infrastructure/vendor_ws/realtime_ws_client.py
  （RealtimeSessionExecutor A1 的 WS 协议，默认 OpenAI Realtime 事件协议）

会话语义：
- 会话建立  客户端 session.update → 服务端 session.created（可选）+ session.updated
- 逐帧 ack  客户端 input_audio_buffer.append → 服务端回 input_audio_buffer.append.ack
             （per_frame_ack，seq + bytes；客户端按未知事件透传记录进 frame 通道）
- 输入收口  input_audio_buffer.commit → input_audio_buffer.committed + 响应流
             （response.text.delta → response.audio.delta × N → response.done）
- 打断语义  barge_in=true 时首轮 commit 响应结束后预置
             response.audio.delta + input_audio_buffer.speech_started + response.cancelled
- 会话关闭  客户端关闭即结束；disconnect_after_events 注入中途断连

行为可配置（优先级：命令行 > 环境变量 MOCK_RT_* > 配置文件 > 默认值），
运行中可经 WS 控制帧热更新（无需重启）：
- {'type': '__mock_control', 'action': 'set_behavior', 'behavior': {...}}
- {'type': '__mock_control', 'action': 'get'}
- {'type': '__mock_control', 'action': 'reset'}

注入场景：
- 延迟注入       first_delta_delay_ms（commit → 首个 delta 的间隔，可测首帧延迟）
- 中途断连       disconnect_after_events=N（本连接第 N 个客户端事件处理后主动断开）
- 协议错误注入   protocol_error_on_event=<事件类型>（该事件回 error 帧，不执行正常语义）

独立可运行（依赖 websockets，与生产 WS 客户端同环境；端口取 service_ports 注册值）：
    python mock_services/mock_realtime_api.py [--port 5098] [行为参数...]
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import threading
from dataclasses import dataclass, asdict, field
from enum import Enum

# 端口唯一来源：service_ports 注册表（独立运行时回退仓库根导入）
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.config.service_ports import MOCK_REALTIME_API_WS_PORT  # noqa: E402

DEFAULT_PORT = MOCK_REALTIME_API_WS_PORT

# WS 控制帧（mock 自有协议，客户端按未知事件透传，不进生产契约）
CONTROL_EVENT_TYPE = '__mock_control'
CONTROL_REPLY_TYPE = '__mock_control.reply'


class MockControlAction(str, Enum):
    """WS 控制帧动作。"""
    SET_BEHAVIOR = 'set_behavior'
    GET = 'get'
    RESET = 'reset'


@dataclass
class MockRealtimeBehavior:
    """mock 行为配置（enum 化 + 配置文件 + 命令行 + WS 控制帧热更新）。"""
    session_created: bool = True
    per_frame_ack: bool = True
    auto_response: bool = True
    response_chunks: int = 3
    chunk_interval_ms: int = 20
    first_delta_delay_ms: int = 0
    answer_text: str = 'mock 回复文本'
    barge_in: bool = False
    disconnect_after_events: int = 0
    protocol_error_on_event: str = ''

    def validate(self) -> None:
        if self.response_chunks < 0 or self.response_chunks > 1000:
            raise ValueError(f'非法 response_chunks: {self.response_chunks}（允许 0~1000）')
        if self.first_delta_delay_ms < 0 or self.first_delta_delay_ms > 60000:
            raise ValueError(
                f'非法 first_delta_delay_ms: {self.first_delta_delay_ms}（允许 0~60000）')
        if self.disconnect_after_events < 0 or self.disconnect_after_events > 100000:
            raise ValueError(
                f'非法 disconnect_after_events: {self.disconnect_after_events}（允许 0=关闭）')
        if self.chunk_interval_ms < 0 or self.chunk_interval_ms > 1000:
            raise ValueError(f'非法 chunk_interval_ms: {self.chunk_interval_ms}（允许 0~1000）')

    def update(self, changes: dict) -> None:
        """部分字段热更新（WS 控制帧入口），非法值 fail-closed 整体拒绝。"""
        allowed = {'session_created', 'per_frame_ack', 'auto_response',
                   'response_chunks', 'chunk_interval_ms', 'first_delta_delay_ms',
                   'answer_text', 'barge_in', 'disconnect_after_events',
                   'protocol_error_on_event'}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f'未知行为字段: {sorted(unknown)}（允许 {sorted(allowed)}）')
        candidate = MockRealtimeBehavior(**{**asdict(self), **changes})
        candidate.validate()
        for key, value in asdict(candidate).items():
            setattr(self, key, value)

    @classmethod
    def from_env(cls) -> 'MockRealtimeBehavior':
        prefix = 'MOCK_RT_'
        mapping = {
            'session_created': _env_bool, 'per_frame_ack': _env_bool,
            'auto_response': _env_bool, 'response_chunks': int,
            'chunk_interval_ms': int, 'first_delta_delay_ms': int,
            'answer_text': str, 'barge_in': _env_bool,
            'disconnect_after_events': int, 'protocol_error_on_event': str,
        }
        kwargs = {}
        for key, cast in mapping.items():
            raw = os.environ.get(prefix + key.upper())
            if raw is not None and raw != '':
                kwargs[key] = cast(raw)
        return cls(**kwargs)

    @classmethod
    def from_config_file(cls, path: str) -> 'MockRealtimeBehavior':
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f) or {}
        behavior = data.get('behavior') or data
        return cls(**behavior)


def _env_bool(raw: str) -> bool:
    return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')


@dataclass
class MockRealtimeState:
    """服务端可观测状态（客户端事件流 / 发送事件计数 / 连接数）。"""
    received: list = field(default_factory=list)   # 客户端事件类型（时间序）
    sent: dict = field(default_factory=dict)       # 服务端发出事件类型 -> 次数
    connections: int = 0
    responses_streamed: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record_received(self, event_type: str) -> None:
        with self.lock:
            self.received.append(event_type)

    def record_sent(self, event_type: str) -> None:
        with self.lock:
            self.sent[event_type] = self.sent.get(event_type, 0) + 1

    def snapshot(self) -> dict:
        with self.lock:
            return {
                'received': list(self.received),
                'sent': dict(self.sent),
                'connections': self.connections,
                'responses_streamed': self.responses_streamed,
            }

    def reset(self) -> None:
        with self.lock:
            self.received.clear()
            self.sent.clear()
            self.connections = 0
            self.responses_streamed = 0


class MockRealtimeSession:
    """单连接会话状态（响应流计数 / barge-in 预置标记）。"""

    def __init__(self):
        self.append_seq = 0
        self.commits = 0
        self.barge_in_prequeued = False
        self.events_in_connection = 0


class MockRealtimeService:
    """行为与状态持有者（handler 与控制帧共享，运行于事件循环线程）。"""

    def __init__(self, behavior: MockRealtimeBehavior):
        self.behavior = behavior
        self.state = MockRealtimeState()

    async def handle_connection(self, ws) -> None:
        """WS 连接处理：事件循环 → 正常语义 / 注入 → 收口。"""
        self.state.connections += 1
        session = MockRealtimeSession()
        try:
            async for raw in ws:
                event = json.loads(raw)
                etype = str(event.get('type') or '')
                session.events_in_connection += 1
                self.state.record_received(etype)

                if etype == CONTROL_EVENT_TYPE:
                    await self._handle_control(ws, event)
                elif self._is_protocol_error_triggered(etype):
                    await self._send(ws, {
                        'type': 'error',
                        'error': {'code': 'mock_protocol_error',
                                  'message': f'mock 注入协议错误（触发事件: {etype}）'},
                    })
                elif etype == 'session.update':
                    await self._handle_session_update(ws)
                elif etype == 'input_audio_buffer.append':
                    await self._handle_append(ws, session, event)
                elif etype == 'input_audio_buffer.commit':
                    await self._handle_commit(ws, session)
                elif etype == 'response.create':
                    if self.behavior.auto_response:
                        await self._stream_response(ws)
                # 其余客户端事件：记录后忽略（对齐厂商宽松语义）

                if self._should_disconnect(session):
                    await ws.close()
                    return
        except Exception:
            # 客户端断开/网络异常：连接结束（状态已记录，不外抛污染事件循环）
            pass

    # ---- 事件语义 ----
    async def _handle_session_update(self, ws) -> None:
        if self.behavior.session_created:
            await self._send(ws, {'type': 'session.created'})
        await self._send(ws, {'type': 'session.updated'})

    async def _handle_append(self, ws, session: MockRealtimeSession, event: dict) -> None:
        if not self.behavior.per_frame_ack:
            return
        session.append_seq += 1
        audio = str(event.get('audio') or '')
        await self._send(ws, {
            'type': 'input_audio_buffer.append.ack',
            'seq': session.append_seq,
            'bytes': len(base64.b64decode(audio)) if audio else 0,
        })

    async def _handle_commit(self, ws, session: MockRealtimeSession) -> None:
        session.commits += 1
        await self._send(ws, {'type': 'input_audio_buffer.committed'})
        if self.behavior.auto_response:
            await self._stream_response(ws)
        if self.behavior.barge_in and not session.barge_in_prequeued:
            # 预置"AI 正在说话 + 打断"事件序列（对齐既有集成测试伪厂商模式，
            # 供下一轮打断轮 wait_ai_speaking / barge-in 窗口消费）
            session.barge_in_prequeued = True
            await self._send(ws, {'type': 'response.audio.delta',
                                  'delta': _pcm_delta_b64()})
            await self._send(ws, {'type': 'input_audio_buffer.speech_started'})
            await self._send(ws, {'type': 'response.cancelled'})

    async def _stream_response(self, ws) -> None:
        """响应流：可选延迟 → text.delta → audio.delta × N → done（单一 done 收口）。"""
        behavior = self.behavior
        if behavior.first_delta_delay_ms > 0:
            await asyncio.sleep(behavior.first_delta_delay_ms / 1000.0)
        await self._send(ws, {'type': 'response.text.delta', 'delta': behavior.answer_text})
        for index in range(behavior.response_chunks):
            await self._send(ws, {'type': 'response.audio.delta', 'delta': _pcm_delta_b64()})
            if index < behavior.response_chunks - 1 and behavior.chunk_interval_ms > 0:
                await asyncio.sleep(behavior.chunk_interval_ms / 1000.0)
        await self._send(ws, {'type': 'response.done'})
        self.state.responses_streamed += 1

    # ---- 注入判定 ----
    def _is_protocol_error_triggered(self, event_type: str) -> bool:
        trigger = self.behavior.protocol_error_on_event
        return bool(trigger) and event_type == trigger

    def _should_disconnect(self, session: MockRealtimeSession) -> bool:
        threshold = self.behavior.disconnect_after_events
        return bool(threshold) and session.events_in_connection >= threshold

    # ---- 控制帧 ----
    async def _handle_control(self, ws, event: dict) -> None:
        action = str(event.get('action') or MockControlAction.GET.value)
        reply = {'type': CONTROL_REPLY_TYPE, 'action': action}
        try:
            if action == MockControlAction.SET_BEHAVIOR.value:
                self.behavior.update(dict(event.get('behavior') or {}))
                reply['behavior'] = asdict(self.behavior)
            elif action == MockControlAction.GET.value:
                reply['behavior'] = asdict(self.behavior)
                reply['state'] = self.state.snapshot()
            elif action == MockControlAction.RESET.value:
                self.state.reset()
                reply['state'] = self.state.snapshot()
            else:
                reply['error'] = f'非法控制动作: {action}'
        except ValueError as e:
            reply['error'] = str(e)
        await self._send(ws, reply)

    async def _send(self, ws, payload: dict) -> None:
        await ws.send(json.dumps(payload, ensure_ascii=False))
        self.state.record_sent(str(payload.get('type') or ''))

    def snapshot(self) -> dict:
        return {'behavior': asdict(self.behavior), 'state': self.state.snapshot()}


def _pcm_delta_b64() -> str:
    """一小段方波 PCM（s16，80 字节）的 base64 —— 仅做流量载荷，无音频语义。"""
    return base64.b64encode(b'\x01\x02' * 40).decode('ascii')


class MockRealtimeServer:
    """可编程启停的 mock Realtime WS 服务器（进程内测试 / 独立进程运行共用）。"""

    def __init__(self, behavior: MockRealtimeBehavior = None, host: str = '127.0.0.1',
                 port: int = 0):
        self.service = MockRealtimeService(behavior or MockRealtimeBehavior())
        self.host = host
        self._requested_port = port
        self._port = port
        self._server = None
        self._loop = None
        self._thread = None
        self._started = threading.Event()

    @property
    def port(self) -> int:
        return self._port

    @property
    def url(self) -> str:
        return f'ws://{self.host}:{self.port}'

    def start(self):
        import websockets

        async def serve():
            self._server = await websockets.serve(
                self.service.handle_connection, self.host, self._requested_port)
            self._port = self._server.sockets[0].getsockname()[1]
            self._started.set()
            await self._server.serve_forever()

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_until_complete, args=(serve(),), daemon=True,
            name='mock-realtime-api')
        self._thread.start()
        assert self._started.wait(timeout=5), 'mock realtime 服务器启动超时'

    def stop(self):
        if self._server is not None and self._loop is not None:
            async def _close():
                self._server.close()
                await self._server.wait_closed()
            asyncio.run_coroutine_threadsafe(_close(), self._loop).result(timeout=5)
        if self._thread is not None:
            self._thread.join(timeout=5)

    def set_behavior(self, changes: dict) -> None:
        """跨线程热更新行为（测试驱动注入用；独立进程用 WS 控制帧）。"""
        self.service.behavior.update(changes)

    def wait_until_interrupted(self) -> None:
        """阻塞当前（主）线程直至 KeyboardInterrupt —— 事件循环运行在后台线程。"""
        stop_event = threading.Event()
        try:
            stop_event.wait()
        except KeyboardInterrupt:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Mock Realtime API 服务（WS 替身）')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--config', default='',
                        help='行为配置文件（JSON，behavior 段；优先级低于命令行与环境变量）')
    parser.add_argument('--no-session-created', action='store_true')
    parser.add_argument('--no-per-frame-ack', action='store_true')
    parser.add_argument('--no-auto-response', action='store_true')
    parser.add_argument('--response-chunks', type=int)
    parser.add_argument('--chunk-interval-ms', type=int)
    parser.add_argument('--first-delta-delay-ms', type=int)
    parser.add_argument('--answer-text')
    parser.add_argument('--barge-in', action='store_true')
    parser.add_argument('--disconnect-after-events', type=int)
    parser.add_argument('--protocol-error-on-event')
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    behavior = (MockRealtimeBehavior.from_config_file(args.config)
                if args.config else MockRealtimeBehavior.from_env())
    cli_changes = {}
    if args.no_session_created:
        cli_changes['session_created'] = False
    if args.no_per_frame_ack:
        cli_changes['per_frame_ack'] = False
    if args.no_auto_response:
        cli_changes['auto_response'] = False
    if args.response_chunks is not None:
        cli_changes['response_chunks'] = args.response_chunks
    if args.chunk_interval_ms is not None:
        cli_changes['chunk_interval_ms'] = args.chunk_interval_ms
    if args.first_delta_delay_ms is not None:
        cli_changes['first_delta_delay_ms'] = args.first_delta_delay_ms
    if args.answer_text is not None:
        cli_changes['answer_text'] = args.answer_text
    if args.barge_in:
        cli_changes['barge_in'] = True
    if args.disconnect_after_events is not None:
        cli_changes['disconnect_after_events'] = args.disconnect_after_events
    if args.protocol_error_on_event is not None:
        cli_changes['protocol_error_on_event'] = args.protocol_error_on_event
    if cli_changes:
        behavior.update(cli_changes)

    server = MockRealtimeServer(behavior, host=args.host, port=args.port)
    server.start()
    print(f'[mock_realtime_api] listening on ws://{args.host}:{server.port} '
          f'behavior={asdict(behavior)}', flush=True)
    try:
        server.wait_until_interrupted()
    finally:
        server.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())

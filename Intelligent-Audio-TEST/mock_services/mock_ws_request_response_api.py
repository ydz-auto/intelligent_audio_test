# -*- coding: utf-8 -*-
"""Mock WS 请求-响应 API 服务 — 被测产品请求-响应式 WebSocket 替身（INT-2079/A4）。

契约对齐（生产客户端，勿改 mock 侧以外的契约）：
- 客户端：api_test_service/infrastructure/adapters/websocket_adapter.py
  （websocket + streaming=false 的请求-响应式传输）

语义（非会话式，一次连接一次往返）：
- 客户端连接 → 发一条请求 JSON 消息 → 服务端回一条 JSON 响应 → 关闭连接。
- 无 session.update / input_audio_buffer.* / response.* 事件协议（那是
  Realtime 会话式流式能力，不适用于本组合）。

行为可配置（优先级：命令行 > 环境变量 MOCK_WSRR_* > 配置文件 > 默认值）：
- answer_text              响应中的输出文本（data.output / asr_text）
- response                 完整响应 JSON（覆盖 answer_text 派生的默认响应）
- response_delay_ms        收到请求 → 发出响应的延迟（测超时兜底）
- close_after_response     发出响应后是否关闭连接（默认 true）
- disconnect_before_response  收到请求后直接断开（不响应，测断连收敛）
- protocol_error           收到请求后回 error 帧（协议错误注入）
- session_end_mapping 命中  响应中 data.session_end=true（测会话结束标记提前收敛）

独立可运行（依赖 websockets，与生产 WS 客户端同环境；端口取 service_ports 注册值）：
    python mock_services/mock_ws_request_response_api.py [--port 5095] [行为参数...]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, asdict, field
from enum import Enum

# 端口唯一来源：service_ports 注册表（独立运行时回退仓库根导入）
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.config.service_ports import MOCK_WS_REQUEST_RESPONSE_API_PORT  # noqa: E402

DEFAULT_PORT = MOCK_WS_REQUEST_RESPONSE_API_PORT

CONTROL_EVENT_TYPE = '__mock_control'
CONTROL_REPLY_TYPE = '__mock_control.reply'


class MockControlAction(str, Enum):
    """WS 控制帧动作。"""
    SET_BEHAVIOR = 'set_behavior'
    GET = 'get'
    RESET = 'reset'


@dataclass
class MockWsRequestResponseBehavior:
    """mock 行为配置（enum 化 + 配置文件 + 命令行 + WS 控制帧热更新）。"""
    answer_text: str = 'mock 请求-响应回复文本'
    response: dict = field(default_factory=dict)
    response_delay_ms: int = 0
    close_after_response: bool = True
    disconnect_before_response: bool = False
    protocol_error: bool = False
    session_end: bool = False

    def validate(self) -> None:
        if self.response_delay_ms < 0 or self.response_delay_ms > 60000:
            raise ValueError(
                f'非法 response_delay_ms: {self.response_delay_ms}（允许 0~60000）')
        if not isinstance(self.answer_text, str):
            raise ValueError('answer_text 必须为字符串')

    def update(self, changes: dict) -> None:
        """部分字段热更新（WS 控制帧入口），非法值 fail-closed 整体拒绝。"""
        allowed = {'answer_text', 'response', 'response_delay_ms',
                   'close_after_response', 'disconnect_before_response',
                   'protocol_error', 'session_end'}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f'未知行为字段: {sorted(unknown)}（允许 {sorted(allowed)}）')
        candidate = MockWsRequestResponseBehavior(**{**asdict(self), **changes})
        candidate.validate()
        for key, value in asdict(candidate).items():
            setattr(self, key, value)

    @classmethod
    def from_env(cls) -> 'MockWsRequestResponseBehavior':
        prefix = 'MOCK_WSRR_'
        mapping = {
            'answer_text': str, 'response': json.loads,
            'response_delay_ms': int, 'close_after_response': _env_bool,
            'disconnect_before_response': _env_bool,
            'protocol_error': _env_bool, 'session_end': _env_bool,
        }
        kwargs = {}
        for key, cast in mapping.items():
            raw = os.environ.get(prefix + key.upper())
            if raw is not None and raw != '':
                kwargs[key] = cast(raw)
        return cls(**kwargs)

    @classmethod
    def from_config_file(cls, path: str) -> 'MockWsRequestResponseBehavior':
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f) or {}
        return cls(**data)

    def build_response(self) -> dict:
        """派生响应：显式 response 优先，否则由 answer_text / session_end 组装。"""
        if self.response:
            return dict(self.response)
        data = {
            'output': self.answer_text,
            'asr_text': self.answer_text,
            'trans_text': self.answer_text,
        }
        if self.session_end:
            data['session_end'] = True
        return {'code': 0, 'msg': 'success', 'data': data}


def _env_bool(raw: str) -> bool:
    return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')


@dataclass
class MockWsRequestResponseState:
    """服务端可观测状态（收到的请求 / 发出的响应 / 连接数）。"""
    received_requests: list = field(default_factory=list)
    sent_responses: int = 0
    connections: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record_request(self, request) -> None:
        with self.lock:
            self.received_requests.append(request)

    def record_response(self) -> None:
        with self.lock:
            self.sent_responses += 1

    def snapshot(self) -> dict:
        with self.lock:
            return {
                'received_requests': list(self.received_requests),
                'sent_responses': self.sent_responses,
                'connections': self.connections,
            }

    def reset(self) -> None:
        with self.lock:
            self.received_requests.clear()
            self.sent_responses = 0
            self.connections = 0


class MockWsRequestResponseService:
    """行为与状态持有者（handler 与控制帧共享，运行于事件循环线程）。"""

    def __init__(self, behavior: MockWsRequestResponseBehavior):
        self.behavior = behavior
        self.state = MockWsRequestResponseState()

    async def handle_connection(self, ws) -> None:
        self.state.connections += 1
        try:
            async for raw in ws:
                event = json.loads(raw)
                etype = str(event.get('type') or '')

                if etype == CONTROL_EVENT_TYPE:
                    await self._handle_control(ws, event)
                    continue

                self.state.record_request(event)
                if self.behavior.disconnect_before_response:
                    await ws.close()
                    return
                if self.behavior.response_delay_ms > 0:
                    await asyncio.sleep(self.behavior.response_delay_ms / 1000.0)
                if self.behavior.protocol_error:
                    await self._send(ws, {
                        'type': 'error',
                        'error': {'code': 'mock_protocol_error',
                                  'message': 'mock 注入协议错误'},
                    })
                else:
                    await self._send(ws, self.behavior.build_response())
                if self.behavior.close_after_response:
                    await ws.close()
                    return
                # 保持连接：由客户端静默超时收敛（测 quiet 超时兜底）
        except Exception:
            # 客户端断开/网络异常：连接结束（状态已记录，不外抛污染事件循环）
            pass

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
        self.state.record_response()

    def snapshot(self) -> dict:
        return {'behavior': asdict(self.behavior), 'state': self.state.snapshot()}


class MockWsRequestResponseServer:
    """可编程启停的 mock WS 请求-响应服务器（进程内测试 / 独立进程运行共用）。"""

    def __init__(self, behavior: MockWsRequestResponseBehavior = None,
                 host: str = '127.0.0.1', port: int = 0):
        self.service = MockWsRequestResponseService(
            behavior or MockWsRequestResponseBehavior())
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

        def _run():
            try:
                self._loop.run_until_complete(serve())
            except Exception:
                pass

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=_run, daemon=True, name='mock-ws-request-response')
        self._thread.start()
        assert self._started.wait(timeout=5), 'mock WS 请求-响应服务器启动超时'

    def stop(self):
        if self._server is not None and self._loop is not None:
            try:
                async def _close():
                    self._server.close()
                asyncio.run_coroutine_threadsafe(_close(), self._loop).result(timeout=3)
            except Exception:
                pass
            if self._thread is not None and self._thread.is_alive():
                try:
                    self._loop.call_soon_threadsafe(self._loop.stop)
                except Exception:
                    pass
        if self._thread is not None:
            self._thread.join(timeout=5)

    def set_behavior(self, changes: dict) -> None:
        self.service.behavior.update(changes)

    def wait_until_interrupted(self) -> None:
        """阻塞当前（主）线程直至 KeyboardInterrupt —— 事件循环运行在后台线程。"""
        stop_event = threading.Event()
        try:
            stop_event.wait()
        except KeyboardInterrupt:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Mock WS 请求-响应 API 服务（WS 替身）')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--config', default='',
                        help='行为配置文件（JSON；优先级低于命令行与环境变量）')
    parser.add_argument('--answer-text')
    parser.add_argument('--response', default='',
                        help='完整响应 JSON（覆盖 answer_text 派生）')
    parser.add_argument('--response-delay-ms', type=int)
    parser.add_argument('--no-close-after-response', action='store_true')
    parser.add_argument('--disconnect-before-response', action='store_true')
    parser.add_argument('--protocol-error', action='store_true')
    parser.add_argument('--session-end', action='store_true')
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    behavior = (MockWsRequestResponseBehavior.from_config_file(args.config)
                if args.config else MockWsRequestResponseBehavior.from_env())
    cli_changes = {}
    if args.answer_text is not None:
        cli_changes['answer_text'] = args.answer_text
    if args.response:
        try:
            cli_changes['response'] = json.loads(args.response)
        except json.JSONDecodeError:
            raise SystemExit(f'非法 --response JSON: {args.response}')
    if args.response_delay_ms is not None:
        cli_changes['response_delay_ms'] = args.response_delay_ms
    if args.no_close_after_response:
        cli_changes['close_after_response'] = False
    if args.disconnect_before_response:
        cli_changes['disconnect_before_response'] = True
    if args.protocol_error:
        cli_changes['protocol_error'] = True
    if args.session_end:
        cli_changes['session_end'] = True
    if cli_changes:
        behavior.update(cli_changes)

    server = MockWsRequestResponseServer(behavior, host=args.host, port=args.port)
    server.start()
    print(f'[mock_ws_request_response_api] listening on ws://{args.host}:{server.port} '
          f'behavior={asdict(behavior)}', flush=True)
    try:
        server.wait_until_interrupted()
    finally:
        server.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())

# -*- coding: utf-8 -*-
"""被测 API 的 HTTP 流式传输客户端（A2 / INT-1790）— 基础设施层。

两种线格式，同一套归一事件出口（A0 / INT-1788 §3.2）：

- **SSE**（`text/event-stream`）：按 SSE 规范逐帧解析 `event` / `data` / `id` /
  `retry` 字段；`data:` 多行按 `\\n` 拼接后再 JSON 解析；注释行（`: keep-alive`）
  视为心跳；空行派发一帧。
- **chunked 兜底**（`protocol=http` + `streaming=true`，B0 裁定 §3.2.1 括注）：
  响应不是 `text/event-stream` 时按「一行一个 JSON」分帧，一行一条 message。

归一事件（`recv()` 唯一产物，`payload` 必须是 dict）：

    {"event_type": "message" | "error" | "end_stream" | "heartbeat",
     "seq": 0, "payload": {...}, "ts": 1710000000.123}

终止条件（卡面「断线重连 / 空闲超时 / 连接关闭」显式化）：

| 情形 | 行为 |
|------|------|
| 服务端正常关闭连接（HTTP 流 EOF） | `end_stream`（正常收尾，不算失败） |
| 空闲超时（`idle_timeout_ms` 内无字节） | 允许重连则重连；否则 `error`（`biz_code=504`, `idle timeout`） |
| 传输层异常断开（chunk 解码失败 / 连接重置）且未到 EOF | 同上，`error` 文案 `connection closed without end_stream` |
| 整体时长超 `max_duration_ms` | `error`（`biz_code=504`, `stream duration exceeded`），防挂死 |
| HTTP 非 2xx | 连接即失败：`error_source=sse`、`biz_code=HTTP status`（A0 §3.6） |
| 网络层（DNS / 拒绝 / TLS） | 连接即失败：`error_source=network`、`biz_code=503` |

重连：`reconnect_enabled` 缺省 **false**（A0 §3.5 ④——断流即失败，不做静默重连，
重连会让轮次数不可复现）；开启时按 `retry_ms` 退避、带 `Last-Event-ID` 续读，
次数上限 `max_reconnect_attempts`，用尽转 `error`。每次成功重连吐一条
`heartbeat`（`payload.reconnected=true`），不切轮次。

退避口径（A2 返工 P3-2）：配置的 `retry_ms` 是**上限**，服务端帧里的 `retry:`
只能缩短不能放大，且一律限幅到写侧值域上限 `MAX_RETRY_MS` 与剩余
`max_duration_ms` 之内；等待按片轮询 `abort_check`（任务停止 / 用例移除），
不会整段阻塞到退避结束。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

import requests

from api_test_service.domain.value_objects.sse_policy import (
    SSE_MAX_RECONNECT_ATTEMPTS,
    SSE_MAX_RETRY_MS,
)
from api_test_service.infrastructure.adapters.proxy_utils import build_proxy_url

logger = logging.getLogger(__name__)

SSE_MEDIA_TYPE = 'text/event-stream'

# 归一事件类型（A0 §3.2：只有 4 值，不按厂商事件名扩展）
EVENT_MESSAGE = 'message'
EVENT_ERROR = 'error'
EVENT_END_STREAM = 'end_stream'
EVENT_HEARTBEAT = 'heartbeat'

# 线格式
MODE_SSE = 'sse'
MODE_CHUNKED = 'chunked'
MODE_AUTO = 'auto'

# 错误来源（A0 §3.6 error_source 词表）
SOURCE_SSE = 'sse'
SOURCE_NETWORK = 'network'

# 空闲超时 / 时长超时统一归 504（A0 §3.6「SSE 空闲超时」行）
BIZ_CODE_TIMEOUT = 504
# 线格式非法（非 JSON 帧）按「上游响应不可解析」归 502
BIZ_CODE_BAD_GATEWAY = 502
# 网络层失败归 503（A0 §3.6「网络层」行）
BIZ_CODE_UNAVAILABLE = 503

DEFAULT_IDLE_TIMEOUT_MS = 30000
DEFAULT_RETRY_MS = 1000
DEFAULT_MAX_RECONNECT_ATTEMPTS = 2
DEFAULT_EVENT_NAME_FIELD = 'event'

# 退避等待的轮询片长：等待期间按片回询 abort_check（任务停止 / 用例移除），
# 不整段阻塞到退避结束（A2 返工 P3-2）。
BACKOFF_POLL_INTERVAL_S = 0.2


class HttpStreamClient:
    """HTTP 流式（SSE / chunked）客户端：连接 + 逐行分帧 + 归一事件"""

    def __init__(self, url: str, *, method: str = 'GET',
                 headers: Optional[Dict[str, str]] = None,
                 body: Any = None,
                 timeout: float = 30,
                 idle_timeout_ms: int = DEFAULT_IDLE_TIMEOUT_MS,
                 max_duration_ms: Optional[int] = None,
                 reconnect_enabled: bool = False,
                 retry_ms: int = DEFAULT_RETRY_MS,
                 max_reconnect_attempts: int = DEFAULT_MAX_RECONNECT_ATTEMPTS,
                 proxy_type: Optional[str] = None,
                 proxy_url: Optional[str] = None,
                 mode: str = MODE_AUTO,
                 event_name_field: str = DEFAULT_EVENT_NAME_FIELD,
                 abort_check: Optional[Callable[[], bool]] = None):
        self._url = url
        self._method = (method or 'GET').upper()
        self._headers = dict(headers or {})
        self._body = body
        self._connect_timeout = float(timeout)
        self._idle_timeout_ms = int(idle_timeout_ms)
        self._max_duration_ms = int(max_duration_ms) if max_duration_ms else None
        self._reconnect_enabled = bool(reconnect_enabled)
        # 配置退避是上限：`meta.sse.retry_ms` 已由写侧校验在 [0, 60000] 内，
        # 这里再限幅一次（旧数据 / 直连 SQL 写入可绕过校验）
        self._retry_ms = max(0, min(int(retry_ms), SSE_MAX_RETRY_MS))
        # 线缆 `retry:` 只能缩短、不能放大配置退避（A2 返工 P3-2）
        self._wire_retry_ms: Optional[int] = None
        # 重连次数同口径限幅（旧数据 / 直连 SQL 可绕过写侧校验）
        self._max_reconnect_attempts = max(
            0, min(int(max_reconnect_attempts), SSE_MAX_RECONNECT_ATTEMPTS))
        self._proxy_type = proxy_type
        self._proxy_url = proxy_url
        self._mode = (mode or MODE_AUTO).lower()
        self._event_name_field = (event_name_field or DEFAULT_EVENT_NAME_FIELD).strip() \
            or DEFAULT_EVENT_NAME_FIELD
        self._abort_check = abort_check

        self._resp: Optional[requests.Response] = None
        self._chunks = None
        self._line_buf = b''
        self._started_ts: Optional[float] = None
        self._seq = 0
        self._closed = True
        self._reconnect_count = 0
        self._last_event_id: Optional[str] = None

        # SSE 帧内状态
        self._frame_event = ''
        self._frame_data: List[str] = []

        # 结果面
        self._status_code = 0
        self._error: Optional[str] = None
        self._error_source: Optional[str] = None
        self._biz_code: Optional[int] = None
        self._biz_msg: Optional[str] = None
        self._line_mode = MODE_SSE
        self._events: List[dict] = []

    # ── 连接生命周期 ──
    def connect(self) -> bool:
        """建立流式连接；HTTP 非 2xx / 网络失败返回 False 并落错误面。"""
        self._started_ts = time.time()
        if self._open():
            self._closed = False
            return True
        return False

    def _open(self) -> bool:
        proxies = None
        full_proxy_url = build_proxy_url(self._proxy_type, self._proxy_url)
        if full_proxy_url:
            proxies = {'http': full_proxy_url, 'https': full_proxy_url}

        headers = dict(self._headers)
        if not any(k.lower() == 'accept' for k in headers):
            headers['Accept'] = SSE_MEDIA_TYPE
        if self._last_event_id is not None:
            headers['Last-Event-ID'] = str(self._last_event_id)

        kwargs = {
            'headers': headers,
            'stream': True,
            # (连接超时, 读超时)：读超时即空闲超时（等待字节的上限）
            'timeout': (self._connect_timeout, self._idle_timeout_ms / 1000.0),
            'proxies': proxies,
        }
        if self._method == 'GET':
            if isinstance(self._body, (dict, list)):
                kwargs['params'] = self._body
        elif self._body is not None:
            kwargs['json'] = self._body

        try:
            resp = requests.request(self._method, self._url, **kwargs)
        except Exception as e:  # 连接拒绝 / DNS / TLS / 连接期超时
            self._set_error(SOURCE_NETWORK, BIZ_CODE_UNAVAILABLE,
                            f'网络错误: {e}')
            return False

        self._status_code = resp.status_code
        if not (200 <= resp.status_code < 300):
            self._set_error(SOURCE_SSE, resp.status_code,
                            f'HTTP {resp.status_code}'
                            + self._body_snippet(resp))
            self._close_response()
            return False

        self._resp = resp
        self._chunks = self._iter_chunks(resp)
        self._line_buf = b''
        self._frame_event = ''
        self._frame_data = []
        self._line_mode = self._detect_mode(resp)
        return True

    @staticmethod
    def _iter_chunks(resp, amt: int = 1024):
        """按「有多少读多少」逐块吐字节。

        不能用 ``resp.iter_content(amt)``：对**没有 content-length 的
        close-delimited 流**（SSE 常见形态）urllib3 的 ``read(amt)`` 会阻塞到
        收满 amt 字节或连接关闭，事件就永远出不来（表现为假空闲超时）。
        ``raw.read1`` 返回当前可用字节，chunked / close-delimited 都成立；
        老版本 urllib3 无 ``read1`` 时退回 iter_content。
        """
        raw = getattr(resp, 'raw', None)
        read1 = getattr(raw, 'read1', None)
        if callable(read1):
            while True:
                try:
                    chunk = read1(amt, decode_content=True)
                except TypeError:
                    chunk = read1(amt)
                if not chunk:
                    return
                yield chunk
            return
        for chunk in resp.iter_content(chunk_size=amt):
            if chunk:
                yield chunk

    @staticmethod
    def _body_snippet(resp, limit: int = 200) -> str:
        try:
            resp.encoding = 'utf-8'
            text = (resp.text or '').strip()
        except Exception:
            return ''
        return f': {text[:limit]}' if text else ''

    def _detect_mode(self, resp) -> str:
        if self._mode in (MODE_SSE, MODE_CHUNKED):
            return self._mode
        content_type = (resp.headers.get('Content-Type') or '').lower()
        # chunked 传输兜底：非 event-stream 的流按「一行一个 JSON」分帧
        return MODE_SSE if SSE_MEDIA_TYPE in content_type else MODE_CHUNKED

    def close(self):
        """关闭连接（幂等）"""
        self._closed = True
        self._close_response()

    def _close_response(self):
        if self._resp is not None:
            try:
                self._resp.close()
            except Exception:
                logger.debug('关闭 HTTP 流响应失败', exc_info=True)
        self._resp = None
        self._chunks = None

    # ── 接收方向 ──
    def recv(self) -> dict:
        """取下一条归一事件；流未关闭前不会返回 None。"""
        while True:
            if self._closed:
                return self._emit(EVENT_END_STREAM)

            if (self._max_duration_ms is not None and self._started_ts is not None
                    and (time.time() - self._started_ts) * 1000 > self._max_duration_ms):
                self._closed = True
                self._close_response()
                self._set_error(SOURCE_SSE, BIZ_CODE_TIMEOUT,
                                'stream duration exceeded')
                return self._emit(EVENT_ERROR, {
                    'code': BIZ_CODE_TIMEOUT, 'message': 'stream duration exceeded',
                    'source': SOURCE_SSE})

            try:
                line = self._read_line()
            except _IdleTimeout:
                return self._on_disconnect('idle timeout')
            except _StreamEnded:
                self._closed = True
                self._close_response()
                return self._emit(EVENT_END_STREAM)
            except Exception as e:  # chunk 解码失败 / 连接重置
                return self._on_disconnect(
                    f'connection closed without end_stream: {e}')

            if line is None:
                continue
            event = self._consume_line(line)
            if event is not None:
                return event

    def _read_line(self) -> Optional[str]:
        """读一行（不含换行符）；EOF 抛 _StreamEnded，读超时抛 _IdleTimeout。"""
        while b'\n' not in self._line_buf:
            if self._chunks is None:
                raise _StreamEnded()
            try:
                chunk = next(self._chunks)
            except StopIteration:
                raise _StreamEnded()
            except Exception as e:
                if _is_read_timeout(e):
                    raise _IdleTimeout()
                # 服务端未按 chunk 编码收尾就断开：属异常断开，不是 EOF
                raise ConnectionError(str(e))
            if not chunk:
                continue
            self._line_buf += chunk
        raw, _, self._line_buf = self._line_buf.partition(b'\n')
        return raw.decode('utf-8', errors='replace').rstrip('\r')

    def _consume_line(self, line: str) -> Optional[dict]:
        """消费一行；返回可派发的归一事件或 None（继续读）。"""
        if self._line_mode == MODE_CHUNKED:
            stripped = line.strip()
            if not stripped:
                return None
            return self._emit_payload(stripped, source=MODE_CHUNKED)

        # SSE 规范：空行派发一帧；`:` 开头是注释（心跳）；`field: value`
        if line == '':
            return self._dispatch_frame()
        if line.startswith(':'):
            return self._emit(EVENT_HEARTBEAT, {'comment': line[1:].strip()})
        field, _, value = line.partition(':')
        if value.startswith(' '):
            value = value[1:]
        if field == 'data':
            self._frame_data.append(value)
        elif field == 'event':
            self._frame_event = value
        elif field == 'id':
            if '\x00' not in value:
                self._last_event_id = value
        elif field == 'retry':
            self._apply_wire_retry(value)
        else:
            logger.debug('忽略未知 SSE 字段: %r', field)
        return None

    def _apply_wire_retry(self, value: str):
        """服务端 `retry:` 限幅：只能缩短配置退避，且不超过 `SSE_MAX_RETRY_MS`。

        A2 返工 P3-2：原实现 `self._retry_ms = int(value)` 直接采用线缆值——
        既覆盖写侧已校验的配置，又无上限（`retry: 86400000` ≈ 挂起 24 小时）。
        """
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            logger.debug('忽略非法 SSE retry 字段: %r', value)
            return
        self._wire_retry_ms = max(0, min(parsed, SSE_MAX_RETRY_MS))

    def _dispatch_frame(self) -> Optional[dict]:
        data_lines, self._frame_data = self._frame_data, []
        event_name, self._frame_event = self._frame_event, ''
        if not data_lines:
            # 只有 event:/id: 没有 data: 的帧不产生业务数据（SSE 规范同款）
            return None
        data = '\n'.join(data_lines)
        event = self._emit_payload(data, source=MODE_SSE, event_name=event_name)
        return event

    def _emit_payload(self, data: str, *, source: str,
                      event_name: str = '') -> dict:
        payload = self._parse_payload(data, source=source, event_name=event_name)
        if payload is None:
            return self._emit(EVENT_ERROR, {
                'code': BIZ_CODE_BAD_GATEWAY,
                'message': f'{source} 帧不是合法 JSON 对象',
                'source': SOURCE_SSE,
            })
        return self._emit(EVENT_MESSAGE, payload)

    def _parse_payload(self, data: str, *, source: str,
                       event_name: str) -> Optional[dict]:
        try:
            parsed = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(parsed, dict):
            # 契约：payload 必须是 dict（A0 §3.2）
            return None
        # 事件名键可配置（`meta.sse.event_name_field`，缺省 `event`）：
        # 写侧校验与文档都声明该键可用，执行侧必须按配置写入（A2 返工 P3-1）
        if event_name and self._event_name_field not in parsed:
            parsed[self._event_name_field] = event_name
        if source == MODE_SSE:
            parsed.setdefault('sse_event', event_name)
        return parsed

    # ── 断线处理 ──
    def _on_disconnect(self, reason: str) -> Optional[dict]:
        """空闲超时 / 异常断开：可重连则重连并返回心跳事件，否则落错误并收尾。"""
        if (self._reconnect_enabled
                and self._reconnect_count < self._max_reconnect_attempts
                and (self._max_duration_ms is None or self._started_ts is None
                     or (time.time() - self._started_ts) * 1000 < self._max_duration_ms)):
            self._reconnect_count += 1
            self._close_response()
            if not self._wait_backoff(self._backoff_seconds()):
                # 退避期间收到停止 / 用例移除信号：立即收尾，不等满退避
                self._closed = True
                self._close_response()
                self._set_error(SOURCE_SSE, BIZ_CODE_TIMEOUT,
                                'reconnect aborted by control signal')
                return self._emit(EVENT_ERROR, {
                    'code': BIZ_CODE_TIMEOUT,
                    'message': 'reconnect aborted by control signal',
                    'source': SOURCE_SSE,
                })
            if self._open():
                return self._emit(EVENT_HEARTBEAT, {
                    'reconnected': True,
                    'attempt': self._reconnect_count,
                    'reason': reason,
                })
            # 重连本身失败（网络 / 非 2xx）：保留 _open 落的错误面，不覆盖成空闲超时
            self._closed = True
            self._close_response()
            return self._emit(EVENT_ERROR, {
                'code': self._biz_code if self._biz_code is not None
                else BIZ_CODE_TIMEOUT,
                'message': self._biz_msg or reason,
                'source': self._error_source or SOURCE_SSE,
            })
        self._closed = True
        self._close_response()
        self._set_error(SOURCE_SSE, BIZ_CODE_TIMEOUT, reason)
        return self._emit(EVENT_ERROR, {
            'code': BIZ_CODE_TIMEOUT,
            'message': reason,
            'source': SOURCE_SSE,
        })

    # ── 内部 ──
    def _effective_retry_ms(self) -> int:
        """生效退避（毫秒）：配置为上限，线缆值只可缩短。"""
        if self._wire_retry_ms is None:
            return self._retry_ms
        return min(self._wire_retry_ms, self._retry_ms)

    def _backoff_seconds(self) -> float:
        """本次退避时长（秒）：生效退避且不越过剩余 `max_duration_ms`。"""
        retry_ms = float(self._effective_retry_ms())
        if self._max_duration_ms is not None and self._started_ts is not None:
            remaining_ms = (self._max_duration_ms
                            - (time.time() - self._started_ts) * 1000)
            retry_ms = min(retry_ms, remaining_ms)
        return max(0.0, retry_ms) / 1000.0

    def _wait_backoff(self, seconds: float) -> bool:
        """可中断退避：按片回询 `abort_check`；返回 False 表示控制信号命中。"""
        deadline = time.time() + max(0.0, seconds)
        while True:
            if self._abort_check is not None and self._abort_check():
                return False
            remaining = deadline - time.time()
            if remaining <= 0:
                return True
            time.sleep(min(remaining, BACKOFF_POLL_INTERVAL_S))

    def _set_error(self, source: str, biz_code, biz_msg: str):
        self._error = biz_msg
        self._error_source = source
        self._biz_code = biz_code
        self._biz_msg = biz_msg

    def _emit(self, event_type: str, payload: Optional[dict] = None) -> dict:
        self._seq += 1
        event = {
            'event_type': event_type,
            'seq': self._seq,
            'payload': payload if payload is not None else {},
            'ts': time.time(),
        }
        self._events.append(event)
        return event

    # ── 结果面 ──
    @property
    def output(self) -> dict:
        return {
            'status_code': self._status_code,
            'latency_ms': int((time.time() - self._started_ts) * 1000)
            if self._started_ts else 0,
            'event_count': sum(1 for e in self._events
                               if e['event_type'] == EVENT_MESSAGE),
            'events': self._events,
            'line_mode': self._line_mode,
            'error': self._error,
            'error_source': self._error_source,
            'biz_code': self._biz_code,
            'biz_msg': self._biz_msg,
            'retry_count': self._reconnect_count,
            'retry_ms': self._effective_retry_ms(),
            'event_name_field': self._event_name_field,
            'last_event_id': self._last_event_id,
        }

    @property
    def status_code(self) -> int:
        return self._status_code

    @property
    def line_mode(self) -> str:
        return self._line_mode

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def error_source(self) -> Optional[str]:
        return self._error_source

    @property
    def biz_code(self):
        return self._biz_code

    @property
    def biz_msg(self) -> Optional[str]:
        return self._biz_msg


class _StreamEnded(Exception):
    """HTTP 流正常结束（EOF）"""


class _IdleTimeout(Exception):
    """空闲超时（读超时）"""


def _is_read_timeout(exc: BaseException) -> bool:
    """判断异常是否为「读超时」（requests 的不同路径分别抛 ReadTimeout 与
    包装过的 urllib3 ReadTimeoutError，两者都归空闲超时）。"""
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return True
    text = repr(exc)
    return 'ReadTimeoutError' in text or 'Read timed out' in text

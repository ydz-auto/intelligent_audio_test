# -*- coding: utf-8 -*-
"""Realtime 厂商 WebSocket 客户端（INT-61）— 基础设施层

与设计文档 RealtimeAPIAdapter 对称的实例内闭环实现：WS 长连接跨多轮保持，
后台接收线程 → 阻塞事件队列，executor 在执行线程中 recv() 取归一化事件。

- 厂商事件协议默认 OpenAI Realtime（session.update / input_audio_buffer.append /
  response.audio.delta ...），归一化映射见 _EVENT_TYPE_MAP；
  executor 与前端只消费 RealtimeFrameType，不接触厂商字段。
- 帧记录实时写入（不等回复结束），最终聚合经 output 属性按需读取。
- event_listener：executor 注入的帧回调（双通道 frame 推送入口），
  在执行线程的 recv() 中触发，无跨线程竞争。
"""
from __future__ import annotations

import base64
import json
import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from shared.models.common_enums import RealtimeFrameType

logger = logging.getLogger(__name__)

# 厂商原始事件类型 → 归一化帧类型（默认 OpenAI Realtime 事件协议，防腐层映射表）
_EVENT_TYPE_MAP = {
    'session.created': RealtimeFrameType.SESSION_CREATED,
    'session.updated': RealtimeFrameType.SESSION_UPDATED,
    'response.audio.delta': RealtimeFrameType.AI_AUDIO_DELTA,
    'response.audio.done': RealtimeFrameType.AI_AUDIO_DONE,
    'response.done': RealtimeFrameType.AI_AUDIO_DONE,
    'response.text.delta': RealtimeFrameType.AI_TEXT_DELTA,
    'response.text.done': RealtimeFrameType.AI_TEXT_DONE,
    'input_audio_buffer.speech_started': RealtimeFrameType.USER_SPEECH_STARTED,
    'input_audio_buffer.speech_stopped': RealtimeFrameType.USER_SPEECH_STOPPED,
    'response.cancelled': RealtimeFrameType.RESPONSE_CANCELLED,
    'error': RealtimeFrameType.ERROR,
    'input_audio_buffer.committed': RealtimeFrameType.INPUT_COMMITTED,
}


class RealtimeFrame:
    """归一化帧记录 {ts, type, payload}"""

    __slots__ = ('ts', 'type', 'payload')

    def __init__(self, ts: float, ftype: str, payload: Any = None):
        self.ts = ts
        self.type = ftype
        self.payload = payload

    def to_dict(self) -> dict:
        return {'ts': self.ts, 'type': self.type, 'payload': self.payload}


class RealtimeWSClient:
    """厂商 Realtime WS 客户端：连接管理 + 接收线程 + 事件归一化 + 帧记录"""

    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None,
                 vendor: str = 'openai',
                 event_listener: Optional[Callable[[dict], None]] = None,
                 chunk_duration_ms: int = 100):
        self._url = url
        self._headers = headers or {}
        self._vendor = vendor
        self._listener = event_listener
        self._chunk_duration_ms = chunk_duration_ms

        self._ws = None
        self._event_queue: queue.Queue = queue.Queue()
        self._recv_thread: Optional[threading.Thread] = None
        self._connected = False

        # 帧级中间状态（逐帧实时记录）
        self._frames: List[RealtimeFrame] = []
        self._ai_audio_chunks: List[bytes] = []
        self._ai_text_chunks: List[str] = []
        self._raw_event_log: List[dict] = []

        # 首帧延迟 / commit 时间戳
        self._first_frame_ts: Optional[float] = None
        self._commit_ts: Optional[float] = None
        self._latency_ms: Optional[int] = None

        # 会话级状态
        self._ai_complete = False
        self.barge_in_detected = False
        self.barge_in_latency_ms: Optional[int] = None
        self._speech_started_ts: Optional[float] = None

    # ── 连接生命周期 ──
    def connect(self) -> bool:
        """建立 WebSocket 连接并启动后台接收线程"""
        try:
            import websocket  # websocket-client
            self._ws = websocket.create_connection(
                self._url, header=self._headers, timeout=10, enable_multithread=True)
            self._connected = True
        except Exception as e:
            logger.error(f"Realtime WS 连接失败 url={self._url}: {e}")
            self._connected = False
            return False

        self._recv_thread = threading.Thread(
            target=self._recv_loop, name='realtime-ws-recv', daemon=True)
        self._recv_thread.start()
        return True

    def close(self):
        """关闭连接并停止接收线程（幂等）"""
        self._connected = False
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            logger.debug("关闭 Realtime WS 失败", exc_info=True)
        if self._recv_thread is not None:
            self._recv_thread.join(timeout=3)
            self._recv_thread = None
        self._ws = None

    # ── 推送方向（executor → 厂商）──
    def pre_process(self, session_config: Optional[dict] = None,
                    wait_confirm_timeout: float = 10.0) -> bool:
        """发送 session.update 配置会话，等待 session.updated 确认"""
        config = session_config or {}
        self._send_json({
            'type': 'session.update',
            'session': config,
        })
        deadline = time.time() + wait_confirm_timeout
        while time.time() < deadline:
            event = self.recv(timeout=1.0)
            if event.get('type') == RealtimeFrameType.SESSION_UPDATED.value:
                return True
            if event.get('type') == RealtimeFrameType.ERROR.value:
                return False
            if event.get('type') == RealtimeFrameType.CONNECTION_CLOSED.value:
                return False
        return False

    def send_audio_chunk(self, pcm_b64: str):
        """推送 100ms base64 PCM chunk（input_audio_buffer.append）"""
        self._send_json({'type': 'input_audio_buffer.append', 'audio': pcm_b64})

    def commit_input(self):
        """标记输入结束（记录 commit 时间戳，用于首帧延迟计算）"""
        self.mark_commit()
        self._send_json({'type': 'input_audio_buffer.commit'})

    def create_response(self, instructions: Optional[str] = None):
        """请求厂商生成回复"""
        payload: Dict[str, Any] = {'type': 'response.create', 'response': {}}
        if instructions:
            payload['response']['instructions'] = instructions
        self._send_json(payload)

    # ── 接收方向（厂商 → executor）──
    def reset_round_state(self):
        """轮次边界重置：AI 完成标记 / barge-in 状态 / 首帧延迟 / 帧与音频累计。

        连接跨多轮保持，但 _ai_complete 等会话级标记若跨轮残留，
        下一轮 wait_ai_complete 会立即误判完成（INT-61 集成测试实测发现）。
        帧与音频按轮累计，executor 负责跨轮拼接会话级口径。
        """
        self._frames = []
        self._ai_audio_chunks = []
        self._ai_text_chunks = []
        self._raw_event_log = []
        self._first_frame_ts = None
        self._commit_ts = None
        self._latency_ms = None
        self._ai_complete = False
        self.barge_in_detected = False
        self.barge_in_latency_ms = None
        self._speech_started_ts = None

    def recv(self, timeout: float = 5.0) -> dict:
        """从事件队列取一条事件并归一化；超时返回 connection_closed 语义的等待超时事件"""
        try:
            raw_event = self._event_queue.get(timeout=timeout)
        except queue.Empty:
            return {'type': 'recv_timeout', 'ts': time.time()}
        return self._parse_event(raw_event)

    def wait_ai_speaking(self, start_timeout: float = 25.0) -> bool:
        """等 AI 开始说话（首个 ai_audio_delta）"""
        deadline = time.time() + start_timeout
        while time.time() < deadline:
            event = self.recv(timeout=1.0)
            etype = event.get('type')
            if etype == RealtimeFrameType.AI_AUDIO_DELTA.value:
                return True
            if etype in (RealtimeFrameType.CONNECTION_CLOSED.value,
                         RealtimeFrameType.ERROR.value):
                return False
        return False

    def wait_ai_complete(self, start_timeout: float = 25.0,
                         end_timeout: float = 60.0) -> bool:
        """等 AI 完整回复：等开始（ai_audio_delta）→ 等结束（ai_audio_done）"""
        if not self._ai_complete:
            if not self.wait_ai_speaking(start_timeout):
                return False
        deadline = time.time() + end_timeout
        while time.time() < deadline:
            if self._ai_complete:
                return True
            event = self.recv(timeout=1.0)
            etype = event.get('type')
            if etype == RealtimeFrameType.AI_AUDIO_DONE.value:
                return True
            if etype == RealtimeFrameType.CONNECTION_CLOSED.value:
                return False
        return False

    # ── 内部 ──
    def _send_json(self, data: dict):
        if self._ws is None:
            raise ConnectionError("Realtime WS 未连接")
        self._ws.send(json.dumps(data, ensure_ascii=False))

    def _recv_loop(self):
        """后台接收线程：只收消息入队，不做厂商字段解析"""
        while self._connected and self._ws is not None:
            try:
                raw = self._ws.recv()
            except Exception as e:
                if self._connected:
                    self._event_queue.put({
                        'type': RealtimeFrameType.CONNECTION_CLOSED.value,
                        'error': str(e),
                        'ts': time.time(),
                    })
                break
            if raw is None or raw == '':
                continue
            if isinstance(raw, bytes):
                self._event_queue.put({'type': 'binary', 'data': raw, 'ts': time.time()})
                continue
            try:
                event = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Realtime WS 收到非 JSON 文本帧，丢弃")
                continue
            event['ts'] = time.time()
            self._event_queue.put(event)

    def _parse_event(self, event: dict) -> dict:
        """厂商事件 → 归一化事件（防腐层）：记录原始事件 + 帧记录 + 状态副作用"""
        self._raw_event_log.append(event)
        raw_type = event.get('type', 'unknown')
        ntype = _EVENT_TYPE_MAP.get(raw_type, raw_type)
        # str-Enum 成员 isinstance(str) 恒真：统一落为纯字符串值
        if isinstance(ntype, RealtimeFrameType):
            ntype = ntype.value
        ts = event.get('ts', time.time())
        payload: Any = None

        if ntype == RealtimeFrameType.AI_AUDIO_DELTA.value:
            audio_b64 = event.get('delta', '')
            try:
                pcm = base64.b64decode(audio_b64) if audio_b64 else b''
            except Exception:
                pcm = b''
            self._ai_audio_chunks.append(pcm)
            self._mark_first_frame(ts)
            payload = {'size': len(pcm)}
        elif ntype == RealtimeFrameType.AI_TEXT_DELTA.value:
            delta = event.get('delta', '')
            self._ai_text_chunks.append(delta)
            payload = {'delta': delta}
        elif ntype == RealtimeFrameType.AI_AUDIO_DONE.value:
            self._ai_complete = True
        elif ntype == RealtimeFrameType.USER_SPEECH_STARTED.value:
            self.barge_in_detected = True
            self._speech_started_ts = ts
            if self._commit_ts is not None:
                self.barge_in_latency_ms = int((ts - self._commit_ts) * 1000)
        elif ntype == RealtimeFrameType.RESPONSE_CANCELLED.value:
            self.barge_in_detected = True
        elif ntype == RealtimeFrameType.ERROR.value:
            payload = {'message': event.get('error', {}).get('message', str(event.get('error', '')))}

        frame = RealtimeFrame(ts=ts, ftype=ntype, payload=payload)
        self._frames.append(frame)

        normalized = {'type': ntype, 'ts': ts}
        if payload is not None:
            normalized['payload'] = payload
        if self._listener is not None:
            try:
                self._listener(normalized)
            except Exception:
                logger.debug("帧监听回调失败", exc_info=True)
        return normalized

    def _mark_first_frame(self, ts: float):
        """标记首帧时间戳并计算首帧延迟（commit → 首帧）"""
        if self._first_frame_ts is None:
            self._first_frame_ts = ts
            if self._commit_ts is not None:
                self._latency_ms = int((ts - self._commit_ts) * 1000)

    def mark_commit(self):
        self._commit_ts = time.time()

    # ── 输出聚合（executor 唯一取数入口，按需实时聚合）──
    @property
    def output(self) -> dict:
        return {
            'audio': b''.join(self._ai_audio_chunks),
            'text': ''.join(self._ai_text_chunks),
            'frame_results': [f.to_dict() for f in self._frames],
            'event_log': [
                {'ts': e.get('ts'), 'type': e.get('type')} for e in self._raw_event_log
            ],
            'latency_ms': self._latency_ms,
            'ai_complete': self._ai_complete,
            'barge_in_detected': self.barge_in_detected,
            'barge_in_latency_ms': self.barge_in_latency_ms,
        }

    @property
    def frame_results(self) -> List[dict]:
        return [f.to_dict() for f in self._frames]

    @property
    def connected(self) -> bool:
        return self._connected

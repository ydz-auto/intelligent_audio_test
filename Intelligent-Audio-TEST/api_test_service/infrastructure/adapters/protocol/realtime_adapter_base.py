# -*- coding: utf-8 -*-
"""Realtime 协议级适配器 base（INT-497）— 三级体系第二级。

类层次：ApiVendorAdapter (Port) → RealtimeAdapterBase（协议级 base，
protocol=REALTIME）→ 品牌适配器（如 vendors/OpenAIRealtimeAdapter）。

生命周期（Port docstring 与设计文档 02_架构设计.md §3.6）：
    initialize → pre_process → send → recv → post_process → teardown
映射 OpenAI Realtime 会话契约（session.update / input_audio_buffer.append /
commit / response 流），组合复用 RealtimeWSClient 为传输/状态机（方案审计
2026-10-16 拍板第 3 项）：暴露 RealtimeWSClient 同形方法面（connect / close /
pre_process / reset_round_state / send_audio_chunk / commit_input / mark_commit /
create_response / wait_ai_speaking / wait_ai_complete / recv / output），
执行链经注册表分发后可无缝互换，轮次编排零改动。

执行链禁止 import 本包具体适配器，只经 vendor_adapter_registry 分发。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from shared.models.common_enums import (
    APIProtocol,
    AdapterProtocol,
    AdapterVendor,
)
from shared.utils.api_key_provider import resolver_from_config
from shared.utils.config_manager import config_manager

from api_test_service.domain.ports import ApiVendorAdapter
from api_test_service.infrastructure.adapters.registry import register_vendor_adapter
from api_test_service.infrastructure.vendor_ws import RealtimeWSClient

logger = logging.getLogger(__name__)

# 密钥链解析器（UC-0901 扩展流程 3a）：case_config → meta → env 逐级回退，
# 各级键名经 config_manager secrets 段配置
_key_resolver = resolver_from_config(config_manager.get_value)


@register_vendor_adapter
class RealtimeAdapterBase(ApiVendorAdapter):
    """Realtime 协议级 base 适配器 — OpenAI Realtime 会话契约默认实现。

    作为注册表 (REALTIME, ANY) 的同协议基线兜底（resolve 精确未命中时回落）；
    品牌适配器继承本类覆写 vendor 维度与厂商专属配置。
    """

    protocol = AdapterProtocol.REALTIME
    vendor = AdapterVendor.ANY
    # Realtime 会话承载于 WebSocket 传输（APIProtocol 维度，INT-61 分型）
    supported_protocols = (APIProtocol.WEBSOCKET,)

    # 传输层厂商事件协议标识（透传 RealtimeWSClient；默认 OpenAI 事件协议）
    _transport_vendor = 'openai'

    def __init__(self, api_config, case_config=None, endpoint=None,
                 test_case_id=None, task_id=None,
                 headers: Optional[Dict[str, str]] = None,
                 event_listener: Optional[Callable[[dict], None]] = None,
                 chunk_duration_ms: Optional[int] = None,
                 proxy_type: Optional[str] = None,
                 proxy_url: Optional[str] = None):
        self.api_config = api_config
        self.case_config = case_config or {}
        self.endpoint = endpoint or ''
        self._test_case_id = test_case_id
        self._task_id = task_id
        self._headers = headers
        self._event_listener = event_listener
        self._chunk_duration_ms = chunk_duration_ms
        self._proxy_type = proxy_type
        self._proxy_url = proxy_url
        self._client: Optional[RealtimeWSClient] = None

    # ── 传输对象构造（组合复用 RealtimeWSClient）──

    def _build_client(self) -> RealtimeWSClient:
        url = self.endpoint or self._resolve_ws_url(self.api_config)
        headers = self._headers or self._resolve_ws_headers(
            self.api_config, case_api_key=self._case_level_key(self.case_config))
        chunk_ms = self._chunk_duration_ms or int(
            config_manager.get_value('realtime_session', 'chunk_duration_ms', 100))
        return RealtimeWSClient(
            url, headers=headers,
            vendor=self._transport_vendor,
            event_listener=self._event_listener,
            chunk_duration_ms=chunk_ms,
            # INT-839：被测 API 网络代理（websocket-client 代理参数注入）
            proxy_type=self._proxy_type,
            proxy_url=self._proxy_url,
        )

    # ── 生命周期钩子（Port 语义）──

    def initialize(self) -> bool:
        """WS 握手：构造传输对象并建立连接（initialize = connect）"""
        if self._client is not None and self._client.connected:
            return True
        self._client = self._build_client()
        return bool(self._client.connect())

    def connect(self) -> bool:
        """RealtimeWSClient 同形方法面：建立连接（executor 入口）"""
        return self.initialize()

    def pre_process(self, session_config: Optional[dict] = None,
                    wait_confirm_timeout: float = 10.0) -> bool:
        """session.update → 确认 session.updated（executor 入口）"""
        if self._client is None:
            return False
        return self._client.pre_process(session_config, wait_confirm_timeout)

    def send(self, chunk_b64: str) -> None:
        """推送一个音频 chunk（input_audio_buffer.append，单帧粒度）"""
        self.send_audio_chunk(chunk_b64)

    def recv(self, timeout: float = 5.0) -> dict:
        """从事件队列取一条归一化事件（超时返回 recv_timeout 语义）"""
        if self._client is None:
            return {'type': 'connection_closed', 'ts': 0.0, 'error': '未连接'}
        return self._client.recv(timeout)

    def post_process(self) -> dict:
        """聚合轮次/会话输出：audio/text/frame/latency/SPL（executor 取数口）"""
        return dict(self.output)

    def teardown(self) -> None:
        """关闭连接、释放会话绑定（幂等）"""
        self.close()

    # ── RealtimeWSClient 同形方法面（executor 轮次编排直接消费）──

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def reset_round_state(self) -> None:
        self._client.reset_round_state()

    def send_audio_chunk(self, pcm_b64: str) -> None:
        self._client.send_audio_chunk(pcm_b64)

    def commit_input(self) -> None:
        self._client.commit_input()

    def mark_commit(self) -> None:
        self._client.mark_commit()

    def create_response(self, instructions: Optional[str] = None) -> None:
        self._client.create_response(instructions)

    def wait_ai_speaking(self, start_timeout: float = 25.0,
                         stop_check: Optional[Callable[[], bool]] = None) -> bool:
        return self._client.wait_ai_speaking(start_timeout, stop_check=stop_check)

    def wait_ai_complete(self, start_timeout: float = 25.0,
                         end_timeout: float = 60.0,
                         stop_check: Optional[Callable[[], bool]] = None) -> bool:
        return self._client.wait_ai_complete(
            start_timeout, end_timeout, stop_check=stop_check)

    # ── 输出聚合（executor 唯一取数入口）──

    @property
    def output(self) -> dict:
        if self._client is None:
            return {'audio': b'', 'text': '', 'frame_results': [],
                    'event_log': [], 'latency_ms': None, 'ai_complete': False,
                    'barge_in_detected': False, 'barge_in_latency_ms': None}
        return self._client.output

    @property
    def frame_results(self) -> List[dict]:
        return self._client.frame_results if self._client else []

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.connected

    # ── HTTP 执行契约不适用（Realtime 走生命周期方法面）──

    def render_request_parts(self, context_data: Dict[str, Any]):
        raise NotImplementedError(
            "Realtime 适配器不走 HTTP 请求渲染契约；请使用生命周期方法面"
            "（initialize/pre_process/send/recv/post_process/teardown）")

    def execute(self, context_data: Dict[str, Any], files=None, method=None):
        raise NotImplementedError(
            "Realtime 适配器不经 execute() 调用；请使用生命周期方法面"
            "（initialize/pre_process/send/recv/post_process/teardown）")

    # ── 连接解析辅助（与 RealtimeSessionExecutor 静态方法同语义，自包含）──

    def _resolve_ws_url(self, api_config) -> str:
        """解析 WS 连接地址：api_endpoints 优先 ws://wss://，回退 endpoint"""
        for source in (list(getattr(api_config, 'api_endpoints', None) or []),):
            for ep in source:
                url = (ep.get('endpoint') or '') if isinstance(ep, dict) else str(ep)
                if url.startswith(('ws://', 'wss://')):
                    return url
        url = getattr(api_config, 'endpoint', None) or ''
        if url.startswith(('ws://', 'wss://')):
            return url
        raise ValueError(
            f"API {getattr(api_config, 'id', '?')} 未配置 WebSocket 端点"
            "（需 ws:// 或 wss:// 前缀）")

    def _case_level_key(self, case_config) -> str:
        """密钥链 case 层候选：用例 api 段优先，回退用例顶层（键名可配置）"""
        return (case_config or {}).get(_key_resolver.case_key) or ''

    def _resolve_ws_headers(self, api_config, case_api_key: str = '') -> dict:
        """解析 WS 握手头：meta.ws_headers 直传 + 密钥链注入；显式头优先"""
        meta = getattr(api_config, 'meta', None) or {}
        headers = dict(meta.get('ws_headers') or {})
        api_key = _key_resolver.resolve(case_value=case_api_key, meta=meta)
        if api_key and not any(k.lower() == 'authorization' for k in headers):
            headers['Authorization'] = f'Bearer {api_key}'
        return headers

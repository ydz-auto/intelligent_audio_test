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

厂商差异覆写落点（INT-1299，20 家 API 接入复用；executor 轮次编排零改动）：
    - resolve_round_mode(round_config)  轮次语义归一化（默认 is_interruption 字段，
                                        内部 _as_bool 兼容 int/bool/str）；厂商方言
                                        （barge_in / interrupt 等字段名）覆写本方法
    - pre_process(session_config)       会话握手 / session.update 载荷方言（覆写或重写）
    - recv(timeout)                     事件归一化（默认经 RealtimeWSClient._EVENT_TYPE_MAP
                                        映射，厂商原始事件类型不同覆写）
    - output                            输出聚合（audio/text/latency/barge_in 状态，
                                        厂商字段名差异在此归一化到同形键）
    - wait_ai_speaking / wait_ai_complete   等待语义（默认 OpenAI 事件协议：ai_audio_delta
                                        / ai_audio_done；厂商事件名不同覆写）
    - _build_client()                   私有传输构造（复用 RealtimeWSClient 时覆写构造
                                        参数；不走 RealtimeWSClient 的厂商自行返回同形
                                        传输对象即可无缝接入执行链）
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from shared.models.common_enums import (
    APIProtocol,
    AdapterProtocol,
    AdapterVendor,
    RealtimeRoundMode,
)
from shared.utils.api_key_provider import resolver_from_config
from shared.utils.config_manager import config_manager

from api_test_service.domain.ports import ApiVendorAdapter
from api_test_service.infrastructure.adapters.registry import register_vendor_adapter
from api_test_service.infrastructure.adapters.transport import RealtimeWSClient

logger = logging.getLogger(__name__)

# 密钥链解析器（UC-0901 扩展流程 3a）：case_config → meta → env 逐级回退，
# 各级键名经 config_manager secrets 段配置；INT-1177 密钥池轮换
# （resolve_rotating + 模块级共享 RotationStateStore，跨协议同源）
_key_resolver = resolver_from_config(config_manager.get_value)

# INT-1177 密钥池轮换触发状态码：WS 握手 401/403/429 → 切下一非冷却 key
# （5xx/网络错误明确不轮换，非账号配额问题）
_ROTATION_TRIGGER_STATUS_CODES = {401, 403, 429}


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
        # INT-1177：当前轮换 key（_resolve_ws_headers 解析结果，握手失败冷却用）
        self._current_api_key = ''

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
        """WS 握手：构造传输对象并建立连接（initialize = connect）。

        INT-1177 密钥池：配置 meta.api_keys 轮换池且无 case 层单值时，
        握手 401/403/429 自动切下一非冷却 key 重建 client（重试上限 =
        池内 key 总数；池全冷却立即失败，不空转等待；全失败抛最后错误）。
        执行器层不感知轮换（Domain 层只见解析结果）。
        """
        if self._client is not None and self._client.connected:
            return True
        return self._connect_with_rotation()

    def connect(self) -> bool:
        """RealtimeWSClient 同形方法面：建立连接（executor 入口）"""
        return self.initialize()

    def _connect_with_rotation(self) -> bool:
        """带密钥池轮换的握手重试（无池时单次连接，现状语义）。"""
        if self._case_level_key(self.case_config):
            # case 层单值最高优先（现状不变）：无轮换池，单次连接
            self._client = self._build_client()
            return bool(self._client.connect())
        meta = getattr(self.api_config, 'meta', None) or {}
        pool = _key_resolver.rotating_pool(meta)
        if not pool:
            # 未配置密钥池：单次连接（现状语义）
            self._client = self._build_client()
            return bool(self._client.connect())
        last_status = None
        last_error = ''
        for attempt in range(len(pool)):
            if attempt > 0:
                # 失败后重新解析密钥：丢弃外部传入头，让 _build_client 经
                # _resolve_ws_headers 走共享轮换游标取下一非冷却 key
                # （同源轮换：跨协议/跨路径同一游标）
                self._headers = None
            if self._headers is not None:
                # 首 attempt 沿用外部传入头（executor 预解析结果）：解析其
                # Authorization Bearer key 记录为当前 key，供失败冷却命中
                # 预解析 key（防止 executor→adapter 路径双推进游标 + 首
                # attempt 失败 key 不进冷却）
                self._current_api_key = self._auth_key_from_headers(self._headers)
            self._client = self._build_client()
            if self._client.connect():
                return True
            last_status = getattr(self._client, 'last_handshake_status', None)
            last_error = (getattr(self._client, 'last_handshake_error', '')
                          or '')
            if last_status not in _ROTATION_TRIGGER_STATUS_CODES:
                # 5xx / 网络错误：明确不轮换（非账号配额问题），立即失败
                return False
            _key_resolver.report_failure(
                self.api_config.id, self._current_api_key)
            if not _key_resolver.has_available_rotating_key(
                    self.api_config.id, meta):
                # 池全冷却：立即失败，不空转等待
                break
        raise ConnectionError(
            f"Realtime WS 握手失败 status={last_status}（密钥池轮换耗尽）: "
            f"{last_error or self.endpoint or ''}")

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

    @staticmethod
    def _as_bool(value) -> bool:
        """布尔兼容解析（int/bool/str，单一来源：RealtimeWSClient._as_bool）。"""
        return RealtimeWSClient._as_bool(value)

    def resolve_round_mode(self, round_config) -> RealtimeRoundMode:
        """轮次语义归一化：round_config → 轮次模式（默认 is_interruption 字段）。

        内部经 _as_bool 类型兼容（int/bool/str），'0'/'false' 字符串不再误判打断轮；
        厂商协议方言（barge_in / interrupt 等字段名）覆写本方法，executor 零改动。
        未连接也可调用（纯配置解析，不依赖传输对象）。
        """
        if self._as_bool((round_config or {}).get('is_interruption')):
            return RealtimeRoundMode.INTERRUPTION
        return RealtimeRoundMode.NORMAL

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

    @staticmethod
    def _auth_key_from_headers(headers) -> str:
        """从外部 WS 握手头提取 Bearer key（executor 预解析注入，失败冷却用）。

        _resolve_ws_headers 将解析结果注入 `Authorization: Bearer <key>`；
        显式头优先场景（meta.ws_headers 已含 Authorization）该值非池内 key，
        置冷却亦无害（非池值不参与轮换选择）。
        """
        if not headers:
            return ''
        for k, v in headers.items():
            if str(k).lower() == 'authorization' and isinstance(v, str) \
                    and v.startswith('Bearer '):
                return v[len('Bearer '):].strip()
        return ''

    def _resolve_ws_headers(self, api_config, case_api_key: str = '') -> dict:
        """解析 WS 握手头：meta.ws_headers 直传 + 密钥链注入；显式头优先

        INT-1177：经 resolve_rotating 消费密钥池轮换（传 api_config.id，
        同一 API 跨协议同源轮换游标）；case 层单值最高优先不变。
        """
        meta = getattr(api_config, 'meta', None) or {}
        headers = dict(meta.get('ws_headers') or {})
        api_key = _key_resolver.resolve_rotating(
            api_id=getattr(api_config, 'id', None),
            case_value=case_api_key,
            meta=meta,
        )
        self._current_api_key = api_key or ''
        if api_key and not any(k.lower() == 'authorization' for k in headers):
            headers['Authorization'] = f'Bearer {api_key}'
        return headers

# -*- coding: utf-8 -*-
"""WS 请求-响应式适配器（INT-2079 / A4）— ApiVendorAdapter Port 实现。

注册维度 `(AdapterProtocol.WEBSOCKET, AdapterVendor.ANY)`：websocket + 非流式
（`streaming=false`）组合的传输语义 —— 请求-响应式：发请求消息 → 等响应；
**非会话式**，无打断 / 推流中打断 / 拒识语义（这些是实时（streaming）能力）。

与 RealtimeWSClient 的分工：
- RealtimeWSClient（streaming=true）：会话式 WS 长连接事件流，session.update /
  input_audio_buffer.* / response.* 事件协议，供 RealtimeSessionExecutor 消费；
- 本适配器（streaming=false）：一次调用 = 一次 WS 请求-响应往返（连接 →
  发请求 → 收响应 → 断开），不维护会话状态，供 APISessionExecutor
  （非流式道）逐轮调用 —— 正常轮 / 多轮按 lane 内策略（一轮 = 一次往返）。

请求渲染 / 占位符 / 响应字段映射与 HTTP、gRPC 适配器同口径（body_template +
{{placeholder}}；field_path 与评估映射在上层统一入口处理，C0/C1/C2 不重开）。
"""
from __future__ import annotations

import json
import logging
import time

from shared.models.common_enums import APIProtocol, AdapterProtocol, AdapterVendor
from shared.utils.api_key_provider import (
    endpoint_rotation_key,
    resolver_from_config,
)
from shared.utils.config_manager import config_manager
from shared.utils.path_extractor import extract_by_path

from api_test_service.domain.ports import ApiVendorAdapter
from api_test_service.infrastructure.adapters.proxy_utils import (
    websocket_proxy_kwargs,
)
from api_test_service.infrastructure.adapters.registry import register_vendor_adapter

logger = logging.getLogger(__name__)

# 密钥链解析器（UC-0901 扩展流程 3a）：case_config → meta → env
# OPENAI_API_KEY 逐级回退，各级键名经 config_manager secrets 段配置
_key_resolver = resolver_from_config(config_manager.get_value)


@register_vendor_adapter
class WebSocketAdapter(ApiVendorAdapter):
    """WS 请求-响应式被测 API 适配器（websocket + streaming=false）。

    请求体来自 `body_template`（渲染 `{{placeholder}}`），一次调用建立一次
    连接：发一条请求消息 → 收响应（可多条，直到会话结束标记 / 服务端断开 /
    首响应后静默超时 / max_responses 上限）→ 关闭连接。响应归一 dict 直接
    作为 `raw_response['json']`，`field_path` 与评估映射在上层统一入口处理。
    """

    protocol = AdapterProtocol.WEBSOCKET
    vendor = AdapterVendor.ANY
    supported_protocols = (APIProtocol.WEBSOCKET,)

    def __init__(self, api_config, case_config=None, endpoint=None,
                 test_case_id=None, task_id=None, **_ignored):
        self.api_config = api_config
        self.case_config = case_config or {}
        self.meta = getattr(api_config, 'meta', None) or {}
        self._test_case_id = test_case_id
        self._task_id = task_id
        self._endpoint = endpoint or self._resolve_ws_url(api_config)
        if not self._endpoint:
            raise ValueError(
                f"API {getattr(api_config, 'id', '?')} 未配置 WebSocket 端点"
                "（需 ws:// 或 wss:// 前缀）")

    # ── 端点 / 头 ──

    @staticmethod
    def _resolve_ws_endpoint(api_config) -> dict:
        """api_endpoints 中首个 ws://wss:// endpoint dict（含 api_keys 池）。"""
        for ep in (getattr(api_config, 'api_endpoints', None) or []):
            url = (ep.get('endpoint') or '') if isinstance(ep, dict) else str(ep)
            if url.startswith(('ws://', 'wss://')):
                return ep if isinstance(ep, dict) else {'endpoint': str(ep)}
        return {}

    @classmethod
    def _resolve_ws_url(cls, api_config) -> str:
        endpoint = cls._resolve_ws_endpoint(api_config)
        return (endpoint or {}).get('endpoint', '') or ''

    def _resolve_ws_headers(self, case_api_key: str = '') -> dict:
        """WS 握手头：meta.ws_headers 直传 + 密钥链注入；显式头优先。

        INT-1177（endpoint 级）：经 resolve_rotating 消费**当前 ws 端点**的
        api_keys 轮换池（传 `(api_id, ws endpoint URL)` 轮换 key，同一端点
        跨协议同源轮换游标）；case 层单值最高优先不变；未配池回退单值链。
        """
        headers = dict(self.meta.get('ws_headers') or {})
        endpoint = self._resolve_ws_endpoint(self.api_config)
        api_key = _key_resolver.resolve_rotating(
            rotation_key=endpoint_rotation_key(
                getattr(self.api_config, 'id', None),
                (endpoint or {}).get('endpoint', '') or ''),
            endpoint=endpoint,
            case_config=self.case_config if isinstance(self.case_config, dict) else None,
            meta=self.meta,
        )
        if api_key and not any(k.lower() == 'authorization' for k in headers):
            headers['Authorization'] = f'Bearer {api_key}'
        return headers

    def _log(self, level='INFO', content='', **kwargs):
        from shared.utils.log_handler import log_and_emit

        kwargs.setdefault('task_id', self._task_id)
        kwargs.setdefault('test_case_id', self._test_case_id)
        log_and_emit(level=level, module='WebSocketAdapter', content=content, **kwargs)

    # ── 请求渲染 ──

    def _replace_placeholders(self, text, context):
        if not isinstance(text, str):
            return text
        for key, value in (context or {}).items():
            placeholder = '{{' + str(key) + '}}'
            if placeholder in text:
                text = text.replace(placeholder, '' if value is None else str(value))
        return text

    def _render_value(self, value, context):
        """模板值递归渲染：dict / list 逐层下钻，标量交给 `_replace_placeholders`。"""
        if isinstance(value, dict):
            return {key: self._render_value(item, context)
                    for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            rendered = [self._render_value(item, context) for item in value]
            return tuple(rendered) if isinstance(value, tuple) else rendered
        return self._replace_placeholders(value, context)

    def _body_template(self) -> dict:
        template = (self.case_config.get('body_template')
                    or self.meta.get('body_template')
                    or self.meta.get('body')
                    or {})
        return template if isinstance(template, dict) else {}

    def _render_body(self, context) -> dict:
        template = self._body_template()
        if template:
            return {
                key: self._render_value(value, context)
                for key, value in template.items()
            }
        # 无 body_template：整份轮次上下文作为请求消息（对齐 ApiDriverAdapter
        # `_render_payload` 空模板 → `{**context}` 语义，请求-响应式 WS 以
        # 轮次上下文 JSON 为请求体）。
        return dict(context or {})

    def render_request_parts(self, context_data):
        """Port 契约：返回 (rendered_headers, rendered_body)。"""
        headers = self._resolve_ws_headers()
        rendered_headers = {
            key: self._replace_placeholders(value, context_data)
            for key, value in headers.items()
        }
        return rendered_headers, self._render_body(context_data or {})

    # ── WS 请求-响应传输（一轮 = 一次往返） ──

    def _request_response(self, body, headers, timeout=None):
        """WS 请求-响应：连接 → 发请求消息 → 收响应 → 断开。

        非会话式：每次调用独立连接，不跨调用保持会话。收响应可多条，收敛
        条件（任一即结束）：会话结束标记命中 / 服务端主动断开 / 首响应后
        静默超时（`meta.recv_timeout`，默认 2s）/ `meta.max_responses` 上限。
        返回统一响应 dict（status_code / latency / json / all_responses / error）。
        """
        try:
            import websocket  # websocket-client
        except ImportError:
            return {
                'status_code': 500, 'latency': 0, 'raw_response': '',
                'json': {}, 'all_responses': [], 'error': 'websocket-client 库未安装',
            }

        effective_timeout = timeout if timeout is not None else self._timeout()
        recv_timeout = float(self.meta.get('recv_timeout', 2.0))
        max_responses = int(self.meta.get('max_responses', 100))
        start_time = time.time()
        responses = []
        last_json = {}
        error = None
        ws = None
        try:
            ws_proxy_kwargs = websocket_proxy_kwargs(
                getattr(self.api_config, 'proxy_type', None),
                getattr(self.api_config, 'proxy_url', None),
            )
            ws = websocket.create_connection(
                self._endpoint, timeout=effective_timeout,
                header=headers, **ws_proxy_kwargs)
            if body:
                if isinstance(body, (dict, list)):
                    ws.send(json.dumps(body, ensure_ascii=False))
                else:
                    ws.send(str(body))

            ws.settimeout(recv_timeout)
            while len(responses) < max_responses:
                try:
                    msg = ws.recv()
                except websocket.WebSocketTimeoutException:
                    if responses:
                        break  # 首响应后的静默期：请求-响应已收敛
                    error = f'WS 请求-响应超时（{recv_timeout}s 内未收到响应）'
                    break
                except websocket.WebSocketConnectionClosedException:
                    if responses:
                        break  # 服务端已响应后关闭 = 正常收敛
                    error = 'WebSocket 连接已关闭（未收到响应）'
                    break
                if msg is None or msg == '':
                    continue
                responses.append(msg)
                try:
                    msg_json = json.loads(msg)
                except (json.JSONDecodeError, TypeError):
                    continue
                last_json = msg_json
                if self._session_end_matched(msg_json):
                    break
            if error is None and not responses:
                error = 'WS 请求-响应未收到任何响应消息'
        except Exception as e:  # noqa: BLE001 - 连接/握手/发送异常统一收敛为失败
            error = str(e)
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass

        return {
            'status_code': 200 if not error else 500,
            'latency': int((time.time() - start_time) * 1000),
            'raw_response': '\n'.join(responses) if responses else '',
            'json': last_json,
            'all_responses': responses,
            'error': error,
        }

    def _timeout(self) -> int:
        return int(getattr(self.api_config, 'max_timeout', None) or 30) or 30

    def _session_end_matched(self, payload) -> bool:
        """会话结束标记：`meta.session_end_mapping` 路径命中 True（对齐 APIClient）。"""
        path = self.meta.get('session_end_mapping')
        if not path:
            return False
        return extract_by_path(payload, path) is True

    # ── 响应归一 ──

    def _extract_outputs(self, payload):
        """归一 payload → (asr, trans)：result_parser 路径 > asr/trans 映射 > 通用键。"""
        if not isinstance(payload, dict):
            return '', ''
        data = payload.get('data')
        data = data if isinstance(data, dict) else payload
        parser = self.meta.get('result_parser') or {}
        asr = extract_by_path(payload, parser.get('asr_text_path', ''), '')
        trans = extract_by_path(payload, parser.get('trans_text_path', ''), '')
        if not asr:
            asr = extract_by_path(data, self.meta.get('asr_mapping', 'asr_result'))
        if not trans:
            trans = extract_by_path(data, self.meta.get('trans_mapping', 'translation_result'))
        asr = (asr or data.get('asr_text') or data.get('output_content')
               or data.get('output') or payload.get('output') or '')
        trans = (trans or data.get('trans_text') or data.get('translation')
                 or payload.get('translation') or '')
        return str(asr or ''), str(trans or '')

    def _result_from_response(self, resp_info: dict, started: float) -> dict:
        payload = resp_info.get('json')
        payload = payload if isinstance(payload, dict) else {}
        asr, trans = self._extract_outputs(payload)
        # 协议错误帧（`{"type": "error", "error": {...}}`）归一为失败：
        # 与 Realtime 事件协议同口径，不是合法业务响应。
        error_frame = payload.get('type') == 'error'
        transport_error = resp_info.get('error')
        if error_frame:
            err_obj = payload.get('error')
            if isinstance(err_obj, dict):
                transport_error = err_obj.get('message') or str(err_obj)
            else:
                transport_error = str(err_obj or '协议错误帧')
        success = (resp_info.get('status_code') == 200
                   and not transport_error) and not error_frame
        return {
            'success': success,
            'latency': round(time.time() - started, 3),
            'status_code': resp_info.get('status_code'),
            'raw_response': payload,
            'error': transport_error,
            'json': payload,
            'asr': asr,
            'trans': trans,
            'output': asr or trans or payload.get('output', ''),
            'biz_code': payload.get('code', 0),
            'biz_msg': payload.get('msg'),
        }

    def _failure_result(self, started: float, error: str) -> dict:
        return {
            'success': False,
            'latency': round(time.time() - started, 3),
            'status_code': 500,
            'raw_response': None,
            'error': error,
            'json': None,
            'asr': '', 'trans': '', 'output': '',
            'biz_code': None, 'biz_msg': None,
        }

    # ── 调用入口 ──

    def execute(self, context_data, files=None, method=None):
        """Port 契约：单次请求-响应调用（不依赖 voice_llm chat 载荷）。"""
        started = time.time()
        try:
            headers, body = self.render_request_parts(context_data or {})
            resp_info = self._request_response(body, headers)
            return self._result_from_response(resp_info, started)
        except Exception as e:  # noqa: BLE001 - 配置类错误归 config
            return self._failure_result(started, str(e))

    def execute_voice_llm_chat(self, *, session_id, input_type, input_data,
                               source_lang='zh', target_lang='en',
                               context=None, context_for_request=None,
                               algorithm_params=None, case_algorithm_params=None,
                               translation_direction=None, round_number=0,
                               total_rounds=1, task_type='voice_llm',
                               headers=None, timeout=None, **_ignored):
        """多轮非流式（request-response）路径：每轮一次 WS 请求-响应往返。

        与 `GrpcAdapter.execute_voice_llm_chat` 同形结果（供
        `APISessionExecutor._send_via_adapter` 直接消费）：请求体来自
        `body_template`，占位符取轮次上下文；响应归一 dict 放 `raw_response`
        （`_attach_api_output_fields` 的 `json` 字段即归一 payload）。
        头经调用方已渲染（`rendered_headers`，含轮换解析后的 Authorization），
        直接合入避免二次 `_resolve_ws_headers` 推进轮换游标（INT-1178）。
        """
        started = time.time()
        round_context = {
            'session_id': session_id,
            'round_number': round_number,
            'total_rounds': total_rounds,
            'input_text': input_data if input_type == 'text' else '',
            'input_audio': input_data if input_type != 'text' else '',
            'input_type': input_type,
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translation_direction': translation_direction or '',
            'algorithm_type': task_type,
            'context': json.dumps(context or [], ensure_ascii=False),
            'context_for_request': json.dumps(context_for_request or [], ensure_ascii=False),
            'algorithm_params': json.dumps(algorithm_params or [], ensure_ascii=False),
            'case_algorithm_params': json.dumps(case_algorithm_params or {},
                                                ensure_ascii=False),
        }
        try:
            if headers:
                merged_headers = dict(headers)
            else:
                merged_headers = self._resolve_ws_headers()
            body = self._render_body(round_context)
            resp_info = self._request_response(body, merged_headers, timeout=timeout)
            return self._result_from_response(resp_info, started)
        except Exception as e:  # noqa: BLE001 - 配置类错误归 config
            return self._failure_result(started, str(e))


__all__ = ['WebSocketAdapter']

# -*- coding: utf-8 -*-
"""gRPC 协议级适配器（INT-1789 / A1）— ApiVendorAdapter Port 实现。

注册维度 `(AdapterProtocol.GRPC, AdapterVendor.ANY)`：gRPC 没有品牌级方言要求，
一家实现即覆盖全部 gRPC 被测 API；品牌私有 proto 靠 `meta.grpc` 配置承载，
不进代码。

职责（A0 §3.5 / §四）：

- 从 `apis.meta.grpc` 读配置（`proto_object_key` / `proto_sha256` / `proto_size` /
  `service` / `method` / `method_kind` / `metadata` / `deadline_ms`），与 descriptor
  交叉校验，不一致即配置错误（不静默修正）。
- 请求体：`body_template`（JSON）→ `ParseDict`；metadata 支持 `{{placeholder}}`
  占位符替换（与 HTTP 适配器同口径）。
- 响应：`MessageToDict(preserving_proto_field_name=True)` 归一 dict 直接作为
  `raw_response['json']`，`field_path` 与评估映射在上层统一入口处理（C0/C1/C2
  不重开）。
- 错误：gRPC status → `biz_code` / `biz_msg`（`shared.utils.error_mapping`）。

TLS 双向认证本轮不做（insecure + metadata）；server reflection 不做
（`meta.grpc.reflection` 固定 `false`）。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

from shared.models.common_enums import AdapterProtocol, AdapterVendor
from shared.utils.error_mapping import ERROR_SOURCE_CONFIG, config_error_fields
from shared.utils.path_extractor import extract_by_path

from api_test_service.domain.ports import ApiVendorAdapter
from api_test_service.infrastructure.adapters.registry import register_vendor_adapter
from api_test_service.infrastructure.adapters.transport.grpc_client import (
    PROTO_MAX_BYTES,
    GrpcBidiSession,
    GrpcCallError,
    GrpcClient,
    GrpcProtoError,
    load_compiled_proto,
    validate_metadata,
)

logger = logging.getLogger(__name__)

_REQUIRED_CONFIG_KEYS = ('service', 'method', 'method_kind')


@register_vendor_adapter
class GrpcAdapter(ApiVendorAdapter):
    """gRPC 被测 API 适配器（unary / server-stream / bidi）。"""

    protocol = AdapterProtocol.GRPC
    vendor = AdapterVendor.ANY

    def __init__(self, api_config, case_config=None, endpoint=None,
                 test_case_id=None, task_id=None, **_ignored):
        self.api_config = api_config
        self.case_config = case_config or {}
        self.meta = getattr(api_config, 'meta', None) or {}
        self._test_case_id = test_case_id
        self._task_id = task_id
        self._endpoint = endpoint or self._resolve_target(api_config)
        self._method = None
        self._client: Optional[GrpcClient] = None

    # ── 配置 ──
    @staticmethod
    def _resolve_target(api_config) -> str:
        """gRPC target：api_endpoints 首个端点（INT-1361 端点唯一来源）。"""
        for ep in (getattr(api_config, 'api_endpoints', None) or []):
            url = (ep.get('endpoint') or '') if isinstance(ep, dict) else str(ep)
            if url:
                return url
        return getattr(api_config, 'endpoint', '') or ''

    def grpc_config(self) -> dict:
        """读取并校验 `meta.grpc`（缺失/未知键不静默兜底）。"""
        cfg = self.meta.get('grpc')
        if not isinstance(cfg, dict) or not cfg:
            raise GrpcProtoError(
                "缺少 meta.grpc 配置（proto_object_key / service / method / method_kind）")
        missing = [k for k in _REQUIRED_CONFIG_KEYS if not cfg.get(k)]
        if missing:
            raise GrpcProtoError(f"meta.grpc 缺少必填键: {missing}")
        if cfg.get('reflection'):
            raise GrpcProtoError(
                "meta.grpc.reflection 本轮固定 false——server reflection 未实现")
        if not cfg.get('proto_object_key'):
            raise GrpcProtoError(
                "meta.grpc.proto_object_key 必填（本轮只支持上传 .proto，不做反射）")
        method_kind = str(cfg.get('method_kind')).strip().lower()
        if method_kind not in ('unary', 'server_stream', 'bidi'):
            raise GrpcProtoError(
                f"meta.grpc.method_kind 非法: {cfg.get('method_kind')!r}"
                f"（合法值: unary / server_stream / bidi）")
        return cfg

    def _proto_bytes(self, cfg: dict) -> bytes:
        """按 `proto_object_key` 取 .proto 内容，并校验声明的 sha/大小。"""
        key = cfg['proto_object_key']
        from shared.infrastructure.storage import storage

        try:
            data = storage.load_bytes(key)
        except Exception as exc:  # noqa: BLE001
            raise GrpcProtoError(f"proto 文件读取失败: {key}: {exc}")
        if not data:
            raise GrpcProtoError(f"proto 文件为空: {key}")
        if len(data) > PROTO_MAX_BYTES:
            raise GrpcProtoError(
                f"proto 文件超过 {PROTO_MAX_BYTES} 字节上限（实际 {len(data)}）")
        declared_size = cfg.get('proto_size')
        if declared_size is not None and int(declared_size) != len(data):
            raise GrpcProtoError(
                f"proto_size 声明 {declared_size} 与实际 {len(data)} 不符")
        declared_sha = str(cfg.get('proto_sha256') or '').strip().lower()
        if declared_sha:
            import hashlib

            actual = hashlib.sha256(data).hexdigest()
            if actual != declared_sha:
                raise GrpcProtoError(
                    f"proto_sha256 声明与内容不符（实际 {actual}）")
        return data

    def method(self):
        """解析（并缓存）descriptor 里的方法信息。"""
        if self._method is None:
            cfg = self.grpc_config()
            compiled = load_compiled_proto(
                self._proto_bytes(cfg), filename=f"api_{cfg.get('proto_sha256') or 'proto'}.proto")
            self._method = compiled.find_method(
                cfg['service'], cfg['method'], cfg.get('method_kind'))
        return self._method

    @property
    def method_kind(self) -> str:
        return self.method().kind

    def deadline_ms(self) -> int:
        """deadline：meta.grpc.deadline_ms 优先，缺省 = max_timeout × 1000。"""
        cfg = self.grpc_config()
        if cfg.get('deadline_ms') is not None:
            deadline = int(cfg['deadline_ms'])
            if deadline <= 0:
                raise GrpcProtoError(f"meta.grpc.deadline_ms 必须为正数: {deadline}")
            return deadline
        return int(getattr(self.api_config, 'max_timeout', 30) or 30) * 1000

    def _base_metadata(self) -> dict:
        cfg = self.grpc_config()
        return dict(cfg.get('metadata') or {})

    # ── 请求构造 ──
    def _replace_placeholders(self, text, context):
        if not isinstance(text, str):
            return text
        for key, value in (context or {}).items():
            placeholder = '{{' + str(key) + '}}'
            if placeholder in text:
                text = text.replace(placeholder, '' if value is None else str(value))
        return text

    def _body_template(self) -> dict:
        template = (self.case_config.get('body_template')
                    or self.meta.get('body_template')
                    or self.meta.get('body')
                    or {})
        return template if isinstance(template, dict) else {}

    def _render_body(self, context) -> dict:
        template = self._body_template()
        rendered = {}
        for key, value in template.items():
            rendered[key] = self._replace_placeholders(value, context)
        # 模板未声明的上下文键不自动灌入（gRPC 的 request message 字段由 proto
        # 决定，多塞未知键会 ParseDict 报错）；只合并模板。
        return rendered

    def render_request_parts(self, context_data):
        """Port 契约：返回 (rendered_metadata, rendered_body)。"""
        rendered_headers = {
            key: self._replace_placeholders(value, context_data)
            for key, value in self._base_metadata().items()
        }
        return rendered_headers, self._render_body(context_data)

    # ── 调用 ──
    def _client_for(self, metadata: dict) -> GrpcClient:
        if self._client is None:
            self._client = GrpcClient(
                target=self._endpoint,
                method=self.method(),
                metadata=validate_metadata(metadata),
                deadline_ms=self.deadline_ms(),
            )
        return self._client

    def _log(self, level='INFO', content=''):
        from shared.utils.log_handler import log_and_emit

        log_and_emit(level=level, module='GrpcAdapter', content=content,
                     task_id=self._task_id, test_case_id=self._test_case_id)

    def _extract_text(self, payload: dict) -> tuple:
        """归一 payload → (asr, trans)：result_parser 路径 > asr/trans 映射 > 通用键。"""
        if not isinstance(payload, dict):
            return '', ''
        parser = self.meta.get('result_parser') or {}
        asr = extract_by_path(payload, parser.get('asr_text_path', ''), '') if parser else ''
        trans = extract_by_path(payload, parser.get('trans_text_path', ''), '') if parser else ''
        if not asr:
            asr = extract_by_path(payload, self.meta.get('asr_mapping', 'asr_result'))
        if not trans:
            trans = extract_by_path(payload, self.meta.get('trans_mapping', 'translation_result'))
        asr = asr or payload.get('asr_text') or payload.get('output_content') \
            or payload.get('text') or payload.get('output') or ''
        trans = trans or payload.get('trans_text') or payload.get('translation') or ''
        return str(asr or ''), str(trans or '')

    def _result_from_call(self, call_result: dict) -> dict:
        payload = call_result.get('payload') or {}
        asr, trans = self._extract_text(payload)
        return {
            'success': True,
            'latency': round(call_result.get('latency_ms', 0) / 1000.0, 3),
            'status_code': 0,
            'raw_response': payload,
            'json': payload,
            'error': None,
            'asr': asr,
            'trans': trans,
            'output': asr or trans,
            'biz_code': 0,
            'biz_msg': None,
            'error_source': call_result.get('error_source'),
            'raw_code': call_result.get('raw_code', 0),
            'grpc_status': call_result.get('grpc_status', 0),
        }

    def _failure_result(self, fields: dict, latency_s: float, error: str) -> dict:
        return {
            'success': False,
            'latency': round(latency_s, 3),
            'status_code': fields.get('biz_code', 0),
            'raw_response': None,
            'json': None,
            'error': error,
            'asr': '',
            'trans': '',
            'output': '',
            'biz_code': fields.get('biz_code'),
            'biz_msg': fields.get('biz_msg'),
            'error_source': fields.get('error_source'),
            'raw_code': fields.get('raw_code'),
        }

    def _config_failure(self, exc: Exception, started: float) -> dict:
        fields = config_error_fields(str(exc))
        return self._failure_result(fields, time.time() - started, str(exc))

    def execute(self, context_data, files=None, method=None):
        """Port 契约：unary 单次调用（server_stream / bidi 由执行器按方法形态驱动）。"""
        started = time.time()
        try:
            metadata, body = self.render_request_parts(context_data or {})
            if self.method_kind != 'unary':
                raise GrpcProtoError(
                    f"method_kind={self.method_kind} 不能走 unary 执行路径")
            result = self._client_for(metadata).call_unary(body)
            return self._result_from_call(result)
        except GrpcCallError as exc:
            return self._failure_result(exc.fields, time.time() - started, str(exc))
        except (GrpcProtoError, ValueError) as exc:
            return self._config_failure(exc, started)

    def execute_voice_llm_chat(self, *, session_id, input_type, input_data,
                               source_lang='zh', target_lang='en',
                               context=None, context_for_request=None,
                               algorithm_params=None, case_algorithm_params=None,
                               translation_direction=None, round_number=0,
                               total_rounds=1, task_type='voice_llm',
                               headers=None, timeout=None, **_ignored):
        """非流式多轮（unary）路径：每轮一次 gRPC 调用。

        与 `ApiDriverAdapter.execute_voice_llm_chat` 同形结果（供
        `APISessionExecutor._send_via_adapter` 直接消费）：请求体来自
        `body_template`，占位符取轮次上下文；响应归一 dict 放 `raw_response`
        （`_attach_api_output_fields` 的 `json` 字段即归一 payload）。
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
            'algorithm_params': json.dumps(algorithm_params or [], ensure_ascii=False),
            'case_algorithm_params': json.dumps(case_algorithm_params or {},
                                                ensure_ascii=False),
        }
        try:
            metadata, body = self.render_request_parts(round_context)
            if self.method_kind != 'unary':
                raise GrpcProtoError(
                    f"method_kind={self.method_kind} 不能走非流式 unary 路径")
            call_result = self._client_for(metadata).call_unary(body)
            self._log('DEBUG', f"gRPC unary 调用完成 round={round_number} "
                               f"latency={call_result.get('latency_ms')}ms")
            return self._result_from_call(call_result)
        except GrpcCallError as exc:
            self._log('WARNING', f"gRPC unary 调用失败 round={round_number}: {exc}")
            return self._failure_result(exc.fields, time.time() - started, str(exc))
        except Exception as exc:  # noqa: BLE001 - 配置类错误归 config
            return self._config_failure(exc, started)

    # ── 流式（执行器调用）──
    def call_server_stream(self, context: dict) -> dict:
        """server-stream：一次请求，返回归一事件列表（一条消息 = 一条事件）。"""
        started = time.time()
        metadata, body = self.render_request_parts(context)
        return self._client_for(metadata).call_server_stream(body)

    def open_bidi_session(self, context: dict):
        """bidi：建立会话（请求体按轮次上下文另行 `build_body` 渲染）。"""
        metadata, _body = self.render_request_parts(context)
        client = GrpcClient(
            target=self._endpoint,
            method=self.method(),
            metadata=validate_metadata(metadata),
            deadline_ms=self.deadline_ms(),
        )
        return client.open_bidi_session()

    def build_body(self, context: dict) -> dict:
        return self._render_body(context)

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    def __del__(self):  # pragma: no cover - 尽最大努力释放 channel
        try:
            self.close()
        except Exception:
            pass


__all__ = ['GrpcAdapter', 'ERROR_SOURCE_CONFIG', 'GrpcBidiSession']

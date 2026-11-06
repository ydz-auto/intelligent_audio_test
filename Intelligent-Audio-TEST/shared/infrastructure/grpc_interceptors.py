# -*- coding: utf-8 -*-
"""gRPC 拦截器

提供服务端和客户端通用拦截器：
- 日志拦截器：记录 RPC 调用方法、耗时、请求/响应字段内容、异常
- 通过 LOG_GRPC_PAYLOAD 环境变量控制是否打印 payload（默认 True）
"""
import logging
import os
import time
import functools
import json as _json

import grpc


_logger = logging.getLogger(__name__)

# 是否打印请求/响应 payload，通过环境变量 LOG_GRPC_PAYLOAD 控制
_LOG_PAYLOAD = os.environ.get('LOG_GRPC_PAYLOAD', 'true').lower() in ('true', '1', 'yes')

# payload 最大长度（字符），超出截断
_MAX_PAYLOAD_LEN = int(os.environ.get('LOG_GRPC_MAX_PAYLOAD', 2000))


def _format_payload(obj):
    """将 proto 消息对象格式化为可读字符串

    - 对超长字符串字段（如 base64 文件内容、大 JSON）自动摘要
    - 整体超过 _MAX_PAYLOAD_LEN 时截断
    """
    try:
        from google.protobuf.json_format import MessageToDict
        d = MessageToDict(obj, preserving_proto_field_name=True,
                          always_print_fields_with_no_presence=True)
        # 遍历 dict，将超长字段值摘要化
        _truncate_long_values(d, _MAX_FIELD_LEN)
        s = _json.dumps(d, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    if len(s) > _MAX_PAYLOAD_LEN:
        return s[:_MAX_PAYLOAD_LEN] + f'... (truncated, total {len(s)} chars)'
    return s


# 单个字段值超过此长度时摘要化
_MAX_FIELD_LEN = int(os.environ.get('LOG_GRPC_MAX_FIELD', 500))


def _truncate_long_values(d, max_len):
    """递归遍历 dict/list，将超长字符串值替换为摘要"""
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, str) and len(v) > max_len:
                d[k] = v[:max_len] + f'... ({len(v)} chars total)'
            elif isinstance(v, (dict, list)):
                _truncate_long_values(v, max_len)
    elif isinstance(d, list):
        for i, v in enumerate(d):
            if isinstance(v, str) and len(v) > max_len:
                d[i] = v[:max_len] + f'... ({len(v)} chars total)'
            elif isinstance(v, (dict, list)):
                _truncate_long_values(v, max_len)


# ==================== 服务端拦截器 ====================

def _wrap_rpc_handler(handler, wrap_unary, wrap_stream):
    """按 continuation() 返回的 RpcMethodHandler 实际 RPC 形态包装 behavior。

    grpcio>=1.32 的 HandlerCallDetails 仅含 method/invocation_metadata，
    服务端拦截器必须先 continuation(handler_call_details) 取 handler，再按
    其 unary_unary/stream_unary/unary_stream/stream_stream 属性包装——不得
    依赖 handler_call_details 携带方法属性（INT-141 验收 F1/F3：hasattr
    恒 False 曾致三个服务端拦截器全部 no-op）。
    """
    if handler is None:
        return None
    kwargs = dict(request_deserializer=handler.request_deserializer,
                  response_serializer=handler.response_serializer)
    if handler.unary_unary is not None:
        return grpc.unary_unary_rpc_method_handler(wrap_unary(handler.unary_unary), **kwargs)
    if handler.stream_unary is not None:
        return grpc.stream_unary_rpc_method_handler(wrap_unary(handler.stream_unary), **kwargs)
    if handler.unary_stream is not None:
        return grpc.unary_stream_rpc_method_handler(wrap_stream(handler.unary_stream), **kwargs)
    if handler.stream_stream is not None:
        return grpc.stream_stream_rpc_method_handler(wrap_stream(handler.stream_stream), **kwargs)
    return handler


class ServerLogInterceptor(grpc.ServerInterceptor):
    """服务端日志拦截器：记录每个 RPC 调用的方法、耗时、请求/响应 payload"""

    def intercept_service(self, continuation, handler_call_details):
        method = handler_call_details.method

        def _log_unary(behavior):
            @functools.wraps(behavior)
            def wrapper(request, context):
                start = time.monotonic()
                if _LOG_PAYLOAD:
                    try:
                        _logger.info("[gRPC-recv] %s  request: %s", method, _format_payload(request))
                    except Exception as log_e:
                        _logger.debug("[gRPC-recv] %s  (payload log failed: %s)", method, log_e)
                try:
                    resp = behavior(request, context)
                    elapsed_ms = (time.monotonic() - start) * 1000
                    if _LOG_PAYLOAD:
                        try:
                            _logger.info("[gRPC-recv] %s  response in %.1fms: %s", method, elapsed_ms, _format_payload(resp))
                        except Exception:
                            _logger.info("[gRPC-recv] %s  ok in %.1fms", method, elapsed_ms)
                    else:
                        _logger.info("[gRPC-recv] %s  ok in %.1fms", method, elapsed_ms)
                    return resp
                except Exception as e:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    _logger.error("[gRPC-recv] %s  failed in %.1fms: %s", method, elapsed_ms, e)
                    raise
            return wrapper

        def _log_stream(behavior):
            @functools.wraps(behavior)
            def wrapper(request_or_iterator, context):
                start = time.monotonic()
                if _LOG_PAYLOAD:
                    try:
                        _logger.info("[gRPC-recv] %s  stream request: %s",
                                     method, _format_payload(request_or_iterator))
                    except Exception as log_e:
                        _logger.debug("[gRPC-recv] %s  (payload log failed: %s)", method, log_e)
                chunks = 0
                try:
                    for resp in behavior(request_or_iterator, context):
                        chunks += 1
                        yield resp
                    elapsed_ms = (time.monotonic() - start) * 1000
                    _logger.info("[gRPC-recv] %s  stream done in %.1fms (%d chunks)",
                                 method, elapsed_ms, chunks)
                except Exception as e:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    _logger.error("[gRPC-recv] %s  stream failed in %.1fms after %d chunks: %s",
                                  method, elapsed_ms, chunks, e)
                    raise
            return wrapper

        return _wrap_rpc_handler(continuation(handler_call_details),
                                 _log_unary, _log_stream)


# ==================== 客户端拦截器 ====================

class ClientLogInterceptor(grpc.UnaryUnaryClientInterceptor):
    """客户端日志拦截器：记录出站 RPC 调用方法、请求/响应 payload"""

    def intercept_unary_unary(self, continuation, client_call_details, request):
        method = client_call_details.method
        start = time.monotonic()
        if _LOG_PAYLOAD:
            try:
                _logger.info("[gRPC-send] %s  request: %s", method, _format_payload(request))
            except Exception as log_e:
                _logger.debug("[gRPC-send] %s  (payload log failed: %s)", method, log_e)
        try:
            resp = continuation(client_call_details, request)
            elapsed_ms = (time.monotonic() - start) * 1000
            if _LOG_PAYLOAD:
                try:
                    # resp 可能是 _UnaryOutcome，需 .result() 取真正的 proto message
                    payload_obj = resp
                    if hasattr(resp, 'result') and callable(resp.result):
                        try:
                            payload_obj = resp.result()
                        except Exception:
                            _logger.debug("[gRPC-send] %s  resp.result() 取值失败", method, exc_info=True)
                    if hasattr(payload_obj, 'DESCRIPTOR'):
                        _logger.info("[gRPC-send] %s  response in %.1fms: %s", method, elapsed_ms, _format_payload(payload_obj))
                    else:
                        _logger.info("[gRPC-send] %s  ok in %.1fms", method, elapsed_ms)
                except Exception:
                    _logger.info("[gRPC-send] %s  ok in %.1fms", method, elapsed_ms)
            else:
                _logger.info("[gRPC-send] %s  ok in %.1fms", method, elapsed_ms)
            return resp
        except grpc.RpcError as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            _logger.error("[gRPC-send] %s  failed in %.1fms: %s (code=%s)",
                          method, elapsed_ms, e.details(), e.code())
            raise
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            _logger.error("[gRPC-send] %s  error in %.1fms: %s", method, elapsed_ms, e)
            raise


class ClientDeadlineInterceptor(grpc.UnaryUnaryClientInterceptor):
    """客户端 deadline 拦截器：为未显式设置 timeout 的 unary-unary 调用注入默认 deadline。

    背景（INT-54）：依赖服务「接受连接但不响应」（进程驻留但处理线程假死）时，
    无 deadline 的客户端调用在 grpc._channel._blocking 永久阻塞 —— 上层调用点
    try/except 的失败收敛路径（设计上视为可降级，如引擎侧设备事件注册）永不执行，
    调用线程悬挂（集成回归现场：StartTaskLifecycle → _register_task_events_via_grpc
    → device_service 假死 → gateway.post 悬挂 25 分钟+）。

    注入 deadline 后 DEADLINE_EXCEEDED 与 UNAVAILABLE 同为 grpc.RpcError，
    走既有失败收敛路径。规则：
    - 调用方显式传 timeout 的调用不做改写（显式优先）；
    - 默认值取 BaseConfig.GRPC_CLIENT_DEADLINE_SECONDS（环境变量可覆盖）；
    - 已知长耗时的调用点应显式传更大的 timeout；
    - 流式 RPC 不在 unary 拦截范围（渲染等长时操作本就不应设短 deadline）。
    """

    def intercept_unary_unary(self, continuation, client_call_details, request):
        if client_call_details.timeout is not None:
            return continuation(client_call_details, request)
        from shared.infrastructure.config import BaseConfig
        new_details = client_call_details._replace(
            timeout=BaseConfig.GRPC_CLIENT_DEADLINE_SECONDS)
        return continuation(new_details, request)


class ClientWorkerContextInterceptor(grpc.UnaryUnaryClientInterceptor):
    """客户端 worker 上下文拦截器：出站调用自动附加 worker-instance-id metadata。

    task_service 任务工作线程入口 set_worker_instance_id() 后，本进程全部
    出站 gRPC 调用携带归属实例标识；执行服务端从 invocation_metadata 读取，
    写入事件 payload（UC-1001 worker_instance_id 贯通执行链路）。
    """

    def intercept_unary_unary(self, continuation, client_call_details, request):
        from shared.infrastructure.worker_context import worker_instance_id_metadata
        extra = worker_instance_id_metadata()
        if not extra:
            return continuation(client_call_details, request)
        existing = client_call_details.metadata or ()
        new_details = client_call_details._replace(metadata=tuple(existing) + tuple(extra))
        return continuation(new_details, request)


class ClientUserContextInterceptor(grpc.UnaryUnaryClientInterceptor):
    """客户端操作人上下文拦截器：出站调用自动附加 x-user-id metadata（INT-141）。

    api_gateway 请求入口 set_current_user_id()（JWT 解析结果，AUTH_MODE=off
    为 None 不附加），本进程全部出站 gRPC 调用携带操作人标识；下游服务
    servicer 从 invocation_metadata 读取，写入 CUD 操作人列（方案 A）。
    """

    def intercept_unary_unary(self, continuation, client_call_details, request):
        from shared.infrastructure.user_context import user_id_metadata, user_admin_metadata
        extra = user_id_metadata() + user_admin_metadata()
        if not extra:
            return continuation(client_call_details, request)
        existing = client_call_details.metadata or ()
        new_details = client_call_details._replace(metadata=tuple(existing) + tuple(extra))
        return continuation(new_details, request)


class ServerUserContextInterceptor(grpc.ServerInterceptor):
    """服务端操作人上下文拦截器（INT-141）：RPC 入口从 x-user-id metadata
    读取操作人并写入 contextvar，RPC 结束清理（线程池线程复用防串号）。

    服务内代码用 get_current_user_id() 填充 CUD 操作人列；执行引擎工作
    线程入口显式透传（contextvars 不跨线程传播）。
    """

    def intercept_service(self, continuation, handler_call_details):
        def _setup(context):
            from shared.infrastructure.user_context import (
                set_current_user_id, user_id_from_context,
                set_current_user_is_admin, user_is_admin_from_context,
            )
            set_current_user_id(user_id_from_context(context))
            set_current_user_is_admin(user_is_admin_from_context(context))

        def _cleanup():
            from shared.infrastructure.user_context import (
                set_current_user_id, set_current_user_is_admin,
            )
            set_current_user_id(None)
            set_current_user_is_admin(False)

        def _wrap_unary(behavior):
            @functools.wraps(behavior)
            def wrapper(request, context):
                _setup(context)
                try:
                    return behavior(request, context)
                finally:
                    _cleanup()
            return wrapper

        def _wrap_stream(behavior):
            @functools.wraps(behavior)
            def wrapper(request_or_iterator, context):
                _setup(context)
                try:
                    yield from behavior(request_or_iterator, context)
                finally:
                    _cleanup()
            return wrapper

        return _wrap_rpc_handler(continuation(handler_call_details),
                                 _wrap_unary, _wrap_stream)


# ==================== DB scope 拦截器 ====================

class ServerDbScopeInterceptor(grpc.ServerInterceptor):
    """服务端 DB scope 拦截器：在每次 RPC 结束时清理本线程的 DB session。

    取代 `with app.app_context():` 的作用 —— scoped_session 基于
    threading.get_ident()，gRPC 线程内复用、RPC 结束时 remove() 释放回连接池。
    """

    def intercept_service(self, continuation, handler_call_details):
        def _cleanup():
            try:
                from shared.models.database import remove_db_session
                remove_db_session()
            except Exception:
                _logger.debug("gRPC 拦截器清理 DB session 失败", exc_info=True)

        def _wrap_unary(behavior):
            @functools.wraps(behavior)
            def wrapper(request, context):
                try:
                    return behavior(request, context)
                finally:
                    _cleanup()
            return wrapper

        def _wrap_stream(behavior):
            @functools.wraps(behavior)
            def wrapper(request_or_iterator, context):
                try:
                    yield from behavior(request_or_iterator, context)
                finally:
                    _cleanup()
            return wrapper

        return _wrap_rpc_handler(continuation(handler_call_details),
                                 _wrap_unary, _wrap_stream)


# 单例
client_log_interceptor = ClientLogInterceptor()
client_worker_context_interceptor = ClientWorkerContextInterceptor()
client_user_context_interceptor = ClientUserContextInterceptor()
client_deadline_interceptor = ClientDeadlineInterceptor()
server_log_interceptor = ServerLogInterceptor()
server_user_context_interceptor = ServerUserContextInterceptor()
server_db_scope_interceptor = ServerDbScopeInterceptor()

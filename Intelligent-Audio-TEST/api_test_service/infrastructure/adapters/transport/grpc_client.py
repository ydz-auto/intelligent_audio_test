# -*- coding: utf-8 -*-
"""被测 API 的 gRPC 传输件（INT-1789 / A1）— 基础设施层。

职责边界（A0 裁定 §3.5 / §四）：

- **proto 来源**：上传 `.proto` + 动态 descriptor 编译，**不做 server reflection**
  （`meta.grpc.reflection` 固定 `false`）。安全面：单文件 ≤ 256 KB、`import`
  只允许 `google/protobuf/*.proto` 内置 well-known types、只解析不执行
  （不生成 pb2、不 import 生成模块、编译期临时目录用完即删）。
- **请求构造**：`body_template`（JSON dict）经 `ParseDict` 转 request message。
- **响应归一**：`MessageToDict(msg, preserving_proto_field_name=True)` 得到
  snake_case dict（`field_path` 的唯一作用对象），再包成 `NormalizedEvent`。
- **三形态**：unary / server-streaming / bidi-streaming（client-streaming 不做，
  bidi 已覆盖）。TLS 双向认证不做——本轮先 insecure + metadata。
- **错误**：gRPC status → `biz_code` / `biz_msg` 走 `shared.utils.error_mapping`，
  原始码只落 `raw_code` 诊断字段。

执行器只见本文件的对象；协议差异不外溢（devloop §3.1 架构红线）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import re
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional

from shared.utils.error_mapping import (
    ERROR_SOURCE_GRPC,
    ERROR_SOURCE_NETWORK,
    config_error_fields,
    grpc_status_to_biz,
)
from shared.utils.path_extractor import extract_by_path

logger = logging.getLogger(__name__)

# ── proto 安全边界（A0 §3.5③）──────────────────────────────────────────
PROTO_MAX_BYTES = 256 * 1024
ALLOWED_PROTO_IMPORT_PREFIX = 'google/protobuf/'
_PROTO_IMPORT_RE = re.compile(
    r'^\s*import\s+(?:public\s+|weak\s+)?"([^"]+)"\s*;', re.MULTILINE)

# method_kind → (client_streaming, server_streaming)
METHOD_KINDS = {
    'unary': (False, False),
    'server_stream': (False, True),
    'bidi': (True, True),
}

# 归一事件类型（A0 §4.1：只有 4 值，厂商/协议差异不外溢）
EVENT_MESSAGE = 'message'
EVENT_ERROR = 'error'
EVENT_END_STREAM = 'end_stream'
EVENT_HEARTBEAT = 'heartbeat'


class GrpcProtoError(ValueError):
    """proto / 方法解析类配置错误（error_source=config, biz_code=400）。"""


class GrpcMethodKindError(GrpcProtoError):
    """配置的 method_kind 与 descriptor 不符（防配置漂移）。"""


# ── descriptor 编译与缓存 ──────────────────────────────────────────────

_COMPILED_CACHE: Dict[str, 'CompiledProto'] = {}
_CACHE_LOCK = threading.Lock()


def _well_known_include_dir() -> str:
    """grpc_tools 自带的 well-known types include 目录。"""
    import grpc_tools

    return os.path.join(os.path.dirname(grpc_tools.__file__), '_proto')


def validate_proto_imports(proto_text: str) -> List[str]:
    """import 白名单校验：只允许 well-known types，其余一律拒绝。

    返回被允许的 import 列表；存在不允许的 import 时抛 `GrpcProtoError`
    （不允许相对路径 / URL / 本地文件系统路径）。
    """
    imports = _PROTO_IMPORT_RE.findall(proto_text or '')
    rejected = []
    for item in imports:
        path = str(item)
        allowed = (
            path.startswith(ALLOWED_PROTO_IMPORT_PREFIX)
            and path.endswith('.proto')
            and '..' not in path.replace('\\', '/').split('/')
            and '\\' not in path
            and not os.path.isabs(path)
        )
        if not allowed:
            rejected.append(path)
    if rejected:
        raise GrpcProtoError(
            f"proto import 不在白名单内: {rejected}（仅允许 "
            f"{ALLOWED_PROTO_IMPORT_PREFIX}*.proto，禁止相对路径 / URL / 绝对路径）")
    return imports


def compile_proto(proto_bytes: bytes, filename: str = 'api.proto') -> 'CompiledProto':
    """把 .proto 源码编译成 descriptor pool（不落盘、不生成 pb2）。

    编译期在临时目录放源码与 descriptor_set（protoc 只能读文件路径），
    编译完立即删除；产物只有内存里的 DescriptorPool。
    """
    if not proto_bytes:
        raise GrpcProtoError("proto 内容为空")
    if len(proto_bytes) > PROTO_MAX_BYTES:
        raise GrpcProtoError(
            f"proto 文件超过 {PROTO_MAX_BYTES} 字节上限（实际 {len(proto_bytes)}）")
    try:
        proto_text = proto_bytes.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise GrpcProtoError(f"proto 文件不是 UTF-8 文本: {exc}")
    validate_proto_imports(proto_text)

    sha = hashlib.sha256(proto_bytes).hexdigest()
    from grpc_tools import protoc as grpc_protoc

    with tempfile.TemporaryDirectory(prefix='int1789_proto_') as tmpdir:
        src_path = os.path.join(tmpdir, filename)
        with open(src_path, 'wb') as fh:
            fh.write(proto_bytes)
        desc_path = os.path.join(tmpdir, 'descriptor.pb')
        args = [
            'protoc',
            f'-I{tmpdir}',
            f'-I{_well_known_include_dir()}',
            f'--descriptor_set_out={desc_path}',
            '--include_imports',
            filename,
        ]
        rc = grpc_protoc.main(args)
        if rc != 0:
            raise GrpcProtoError(f"proto 编译失败（protoc 返回 {rc}）")
        with open(desc_path, 'rb') as fh:
            descriptor_set_bytes = fh.read()

    return CompiledProto(sha, descriptor_set_bytes)


class CompiledProto:
    """一份已编译 proto 的方法解析视图（按 sha 缓存复用）。"""

    def __init__(self, sha: str, descriptor_set_bytes: bytes):
        self.sha = sha
        self._descriptor_set_bytes = descriptor_set_bytes
        self._pool = None

    @property
    def pool(self):
        if self._pool is None:
            from google.protobuf import descriptor_pb2, descriptor_pool

            file_set = descriptor_pb2.FileDescriptorSet()
            file_set.ParseFromString(self._descriptor_set_bytes)
            pool = descriptor_pool.DescriptorPool()
            # protoc 输出的 file 列表已按依赖拓扑排序，顺序 Add 即可
            for file_proto in file_set.file:
                try:
                    pool.Add(file_proto)
                except Exception:
                    # 同一 pool 内重复添加（well-known types）可忽略
                    logger.debug("descriptor add skipped: %s",
                                 file_proto.name, exc_info=True)
            self._pool = pool
        return self._pool

    def find_method(self, service: str, method: str,
                    method_kind: Optional[str] = None) -> 'GrpcMethod':
        """解析 service/method，并校验 method_kind 与 descriptor 一致。"""
        from google.protobuf import message_factory

        if not service or not method:
            raise GrpcProtoError("meta.grpc.service / method 必填")
        try:
            service_desc = self.pool.FindServiceByName(service)
        except KeyError:
            raise GrpcProtoError(f"proto 中不存在 service: {service!r}")
        method_desc = service_desc.methods_by_name.get(method)
        if method_desc is None:
            raise GrpcProtoError(
                f"service {service!r} 中不存在 method: {method!r}")
        actual = (method_desc.client_streaming, method_desc.server_streaming)
        if method_kind is not None:
            kind = str(method_kind).strip().lower()
            expected = METHOD_KINDS.get(kind)
            if expected is None:
                raise GrpcProtoError(
                    f"未知 method_kind: {method_kind!r}（合法值: "
                    f"{', '.join(sorted(METHOD_KINDS))}）")
            if expected != actual:
                raise GrpcMethodKindError(
                    f"method_kind={kind} 与 descriptor 不符"
                    f"（client_streaming={actual[0]}, "
                    f"server_streaming={actual[1]}）——拒绝配置漂移")
        kind = next((name for name, flags in METHOD_KINDS.items() if flags == actual), None)
        if kind is None:
            raise GrpcProtoError(
                f"{service}/{method} 为 client-streaming（非 bidi），本轮不支持")
        return GrpcMethod(
            sha=self.sha,
            service=service,
            method=method,
            kind=kind,
            input_class=message_factory.GetMessageClass(method_desc.input_type),
            output_class=message_factory.GetMessageClass(method_desc.output_type),
        )


def load_compiled_proto(proto_bytes: bytes,
                        filename: str = 'api.proto') -> CompiledProto:
    """按 sha256 缓存编译结果（同一份 proto 只编译一次）。"""
    sha = hashlib.sha256(proto_bytes or b'').hexdigest()
    with _CACHE_LOCK:
        cached = _COMPILED_CACHE.get(sha)
    if cached is not None:
        return cached
    compiled = compile_proto(proto_bytes, filename=filename)
    with _CACHE_LOCK:
        _COMPILED_CACHE[sha] = compiled
    return compiled


def clear_proto_cache():
    """清空 descriptor 缓存（单测隔离用）。"""
    with _CACHE_LOCK:
        _COMPILED_CACHE.clear()


class GrpcMethod:
    """解析后的一个 gRPC 方法（消息类 + 调用形态）。"""

    __slots__ = ('sha', 'service', 'method', 'kind', 'input_class', 'output_class')

    def __init__(self, sha, service, method, kind, input_class, output_class):
        self.sha = sha
        self.service = service
        self.method = method
        self.kind = kind
        self.input_class = input_class
        self.output_class = output_class

    @property
    def path(self) -> str:
        return f'/{self.service}/{self.method}'


# ── 归一化 ────────────────────────────────────────────────────────────

def message_to_payload(message) -> dict:
    """protobuf message → snake_case dict（`field_path` 的唯一作用对象）。"""
    from google.protobuf import json_format

    if message is None:
        return {}
    return json_format.MessageToDict(
        message, preserving_proto_field_name=True)


def parse_request(payload: dict, method: GrpcMethod):
    """JSON dict → request message（`ParseDict`，未知字段直接报错）。"""
    from google.protobuf import json_format

    message = method.input_class()
    if payload:
        json_format.ParseDict(payload, message)
    return message


def _normalized_event(event_type: str, seq: int, payload: dict) -> dict:
    return {
        'event_type': event_type,
        'seq': seq,
        'payload': payload if isinstance(payload, dict) else {},
        'ts': time.time(),
    }


def validate_metadata(metadata: Optional[dict]) -> List[tuple]:
    """metadata 校验：key 小写、无 CR/LF（A0 §3.5②）。"""
    if not metadata:
        return []
    if not isinstance(metadata, dict):
        raise GrpcProtoError("meta.grpc.metadata 必须是对象")
    pairs = []
    for key, value in metadata.items():
        name = str(key)
        if name != name.lower():
            raise GrpcProtoError(f"metadata key 必须小写: {name!r}")
        text = '' if value is None else str(value)
        if '\r' in text or '\n' in text:
            raise GrpcProtoError(f"metadata {name!r} 的值含 CR/LF")
        pairs.append((name, text))
    return pairs


# ── 调用结果 ──────────────────────────────────────────────────────────

class GrpcCallError(Exception):
    """gRPC 调用失败（携带归一错误字段，供适配器落结果 dict）。"""

    def __init__(self, fields: dict, raw_message: str = ''):
        self.fields = fields
        self.raw_message = raw_message
        super().__init__(f"gRPC 调用失败: {fields.get('biz_msg')} "
                         f"(raw_code={fields.get('raw_code')}) {raw_message}".strip())


def _status_code_of(exc) -> Optional[int]:
    code = getattr(exc, 'code', None)
    if callable(code):
        try:
            status = code()
        except Exception:
            return None
        value = getattr(status, 'value', None)
        if isinstance(value, tuple) and value:
            return int(value[0])
    return None


# 连接建立失败的 details 特征串：gRPC 在「连不上」时可能报 UNAVAILABLE，
# 也可能直接耗尽 deadline 报 DEADLINE_EXCEEDED；A0 §3.6 要求此类归 network / 503。
_NETWORK_MARKERS = (
    'failed to connect to all addresses',
    'connection refused',
    'name resolution',
    'no such host',
    'dns',
    'tls handshake',
)


def _is_network_failure(exc) -> bool:
    details = ''
    getter = getattr(exc, 'details', None)
    if callable(getter):
        try:
            details = str(getter() or '')
        except Exception:
            details = ''
    text = f'{details} {exc}'.lower()
    return any(marker in text for marker in _NETWORK_MARKERS)


def classify_call_exception(exc) -> dict:
    """异常 → 归一错误字段（gRPC status / 网络层两类）。"""
    from shared.utils.error_mapping import network_error_fields

    status_code = _status_code_of(exc)
    if status_code is not None:
        if status_code in (4, 14) and _is_network_failure(exc):
            # 连接建立失败：业务码归 503（A0 §3.6 网络层），原始 status 仍留诊断
            details = getattr(exc, 'details', None)
            reason = details() if callable(details) else str(exc)
            fields = network_error_fields(str(reason or exc))
            fields['raw_code'] = status_code
            return fields
        biz_code, biz_msg = grpc_status_to_biz(status_code)
        return {
            'biz_code': biz_code,
            'biz_msg': biz_msg,
            'error_source': ERROR_SOURCE_GRPC,
            'raw_code': status_code,
        }
    # 非 RpcError：连接建立期错误（DNS / 拒绝 / TLS）→ network
    return network_error_fields(str(exc) or type(exc).__name__)


# ── 客户端 ────────────────────────────────────────────────────────────

DEFAULT_MAX_MESSAGE_BYTES = 16 * 1024 * 1024


class GrpcClient:
    """单个方法上的 gRPC 调用客户端（unary / server-stream / bidi）。

    channel 懒建、可注入（测试复用）；close() 幂等。
    """

    def __init__(self, target: str, method: GrpcMethod,
                 metadata: Optional[List[tuple]] = None,
                 deadline_ms: Optional[int] = None,
                 channel=None,
                 max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES):
        if not target:
            raise GrpcProtoError("gRPC target 不能为空（api_endpoints[].endpoint）")
        self.target = str(target)
        self.method = method
        self.metadata = list(metadata or [])
        self.deadline_ms = deadline_ms
        self._channel = channel
        self._owns_channel = channel is None
        self._max_message_bytes = max_message_bytes
        self._ready = False

    @property
    def deadline_seconds(self) -> Optional[float]:
        if not self.deadline_ms:
            return None
        return max(float(self.deadline_ms) / 1000.0, 0.001)

    def channel(self):
        if self._channel is None:
            import grpc

            self._channel = grpc.insecure_channel(
                self.target,
                options=[
                    ('grpc.max_receive_message_length', self._max_message_bytes),
                    ('grpc.max_send_message_length', self._max_message_bytes),
                ],
            )
        return self._channel

    def close(self):
        if self._channel is not None and self._owns_channel:
            try:
                self._channel.close()
            except Exception:
                logger.debug("关闭 gRPC channel 失败", exc_info=True)
        self._channel = None
        self._ready = False

    def ensure_ready(self):
        """连接就绪探测：连不上归 network / 503（A0 §3.6 网络层）。

        不能只靠调用异常判网络：gRPC 在「连不上」时也可能直接报
        DEADLINE_EXCEEDED，details 只有 "Deadline Exceeded"，与真的慢响应
        无法区分。建立连接前先探一次，判据确定。
        """
        if self._ready:
            return
        import grpc

        from shared.utils.error_mapping import network_error_fields

        timeout = self.deadline_seconds or 5.0
        try:
            grpc.channel_ready_future(self.channel()).result(
                timeout=max(min(timeout, 10.0), 0.05))
        except Exception as exc:  # noqa: BLE001 - 统一归网络层
            raise GrpcCallError(
                network_error_fields(f'无法连接 gRPC target {self.target}: {exc}'),
                str(exc))
        self._ready = True

    # ── unary ──
    def call_unary(self, payload: dict) -> dict:
        """一次请求一条响应：返回归一结果 dict（含归一 payload 与耗时）。"""
        self.ensure_ready()
        request = parse_request(payload, self.method)
        started = time.time()
        callable_ = self.channel().unary_unary(
            self.method.path,
            request_serializer=self.method.input_class.SerializeToString,
            response_deserializer=self.method.output_class.FromString,
        )
        try:
            response = callable_(request, metadata=self.metadata,
                                 timeout=self.deadline_seconds)
        except Exception as exc:  # noqa: BLE001 - 统一归一，不吞分类
            raise GrpcCallError(classify_call_exception(exc), str(exc))
        latency_ms = int((time.time() - started) * 1000)
        return {
            'success': True,
            'latency_ms': latency_ms,
            'payload': message_to_payload(response),
            'messages': [message_to_payload(response)],
            'biz_code': 0,
            'biz_msg': None,
            'error_source': ERROR_SOURCE_GRPC,
            'raw_code': 0,
            'grpc_status': 0,
        }

    # ── server-stream ──
    def call_server_stream(self, payload: dict) -> dict:
        """一次请求多条响应：全部消息收到后返回（消息按 seq 排序）。"""
        self.ensure_ready()
        request = parse_request(payload, self.method)
        started = time.time()
        callable_ = self.channel().unary_stream(
            self.method.path,
            request_serializer=self.method.input_class.SerializeToString,
            response_deserializer=self.method.output_class.FromString,
        )
        events: List[dict] = []
        try:
            responses = callable_(request, metadata=self.metadata,
                                  timeout=self.deadline_seconds)
            for seq, response in enumerate(responses):
                events.append(_normalized_event(
                    EVENT_MESSAGE, seq, message_to_payload(response)))
        except Exception as exc:  # noqa: BLE001
            fields = classify_call_exception(exc)
            # 部分失败：已收到的消息保留（证据），状态按失败归类
            raise GrpcCallError(
                {**fields, 'partial_events': events}, str(exc))
        latency_ms = int((time.time() - started) * 1000)
        return {
            'success': True,
            'latency_ms': latency_ms,
            'messages': [e['payload'] for e in events],
            'events': events,
            'biz_code': 0,
            'biz_msg': None,
            'error_source': ERROR_SOURCE_GRPC,
            'raw_code': 0,
            'grpc_status': 0,
        }

    # ── bidi ──
    def open_bidi_session(self) -> 'GrpcBidiSession':
        return GrpcBidiSession(self)


class GrpcBidiSession:
    """bidi 会话：发送队列 → 请求迭代器；后台读线程 → 归一事件队列。

    读线程模型与 `RealtimeWSClient` 一致（阻塞 recv + 队列），执行器在调用
    线程里 `recv(timeout)` 取事件，不跨线程共享状态机。
    """

    def __init__(self, client: GrpcClient):
        self._client = client
        self._event_queue: queue.Queue = queue.Queue()
        self._send_queue: queue.Queue = queue.Queue()
        self._closed = False
        self._call = None
        self._reader = None
        self._seq = 0
        self._start()

    def _request_iterator(self):
        while True:
            item = self._send_queue.get()
            if item is None:
                return
            yield item

    def _start(self):
        self._client.ensure_ready()
        method = self._client.method
        callable_ = self._client.channel().stream_stream(
            method.path,
            request_serializer=method.input_class.SerializeToString,
            response_deserializer=method.output_class.FromString,
        )
        self._call = callable_(
            self._request_iterator(), metadata=self._client.metadata,
            timeout=self._client.deadline_seconds)
        self._reader = threading.Thread(
            target=self._read_loop, name='grpc-bidi-recv', daemon=True)
        self._reader.start()

    def _read_loop(self):
        try:
            for response in self._call:
                self._event_queue.put(_normalized_event(
                    EVENT_MESSAGE, self._seq, message_to_payload(response)))
                self._seq += 1
            self._event_queue.put(_normalized_event(EVENT_END_STREAM, self._seq, {}))
        except Exception as exc:  # noqa: BLE001
            fields = classify_call_exception(exc)
            self._event_queue.put(_normalized_event(
                EVENT_ERROR, self._seq,
                {'code': fields.get('biz_code'),
                 'message': fields.get('biz_msg'),
                 'source': fields.get('error_source'),
                 **fields}))
            self._event_queue.put(_normalized_event(EVENT_END_STREAM, self._seq, {}))

    def send(self, payload: dict):
        """发送一条请求消息（JSON dict → ParseDict）。"""
        if self._closed:
            raise GrpcCallError(config_error_fields('bidi 会话已关闭'))
        self._send_queue.put(parse_request(payload, self._client.method))

    def close_send(self):
        """半关闭：请求方向结束（服务端仍可继续推消息）。"""
        if not self._closed:
            self._send_queue.put(None)

    def recv(self, timeout: float = 5.0) -> dict:
        """取一条归一事件；超时返回 heartbeat（不是 end_stream）。"""
        try:
            return self._event_queue.get(timeout=timeout)
        except queue.Empty:
            return _normalized_event(EVENT_HEARTBEAT, self._seq, {})

    def close(self):
        self._closed = True
        try:
            self._send_queue.put_nowait(None)
        except Exception:
            logger.debug("bidi 关闭请求方向失败", exc_info=True)
        call = self._call
        if call is not None:
            try:
                call.cancel()
            except Exception:
                logger.debug("bidi cancel 失败", exc_info=True)
        if self._reader is not None:
            self._reader.join(timeout=3)
            self._reader = None
        self._call = None
        self._client.close()

    # 便于执行器/测试读配置
    @property
    def method(self) -> GrpcMethod:
        return self._client.method


def event_payload_text(event: dict, text_path: str = '') -> str:
    """从归一事件里按 `field_path` 取文本（零路径返回空串）。"""
    payload = event.get('payload') if isinstance(event, dict) else None
    if not text_path or not isinstance(payload, dict):
        return ''
    value = extract_by_path(payload, text_path)
    return '' if value is None else str(value)


def dumps_payload(payload: dict) -> str:
    """日志用：归一 payload 摘要（ensure_ascii=False，不截断 JSON 结构）。"""
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        return str(payload)

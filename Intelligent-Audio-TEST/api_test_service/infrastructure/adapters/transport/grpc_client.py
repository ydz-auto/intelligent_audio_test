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

from shared.models.proto_limits import PROTO_MAX_BYTES  # noqa: F401
# ↑ 单一来源在 shared/models/proto_limits.py（INT-1952 上移，网关预检与
#   执行期读取同口径）；此处保留原名字 re-export，既有 import 点不改。
from shared.utils.error_mapping import (
    ERROR_SOURCE_GRPC,
    ERROR_SOURCE_NETWORK,
    config_error_fields,
    grpc_status_to_biz,
)
from shared.utils.path_extractor import extract_by_path

# INT-1953：method_kind 词表归 domain 值对象、proto 上限归 shared（网关侧也要
# 预检，不能反向依赖本服务）；这里保留原名供既有导入，两处都是同一份定义。
from shared.models.proto_limits import PROTO_MAX_BYTES
from api_test_service.domain.value_objects.grpc_meta import METHOD_KINDS

logger = logging.getLogger(__name__)

# ── proto 安全边界（A0 §3.5③）──────────────────────────────────────────
ALLOWED_PROTO_IMPORT_PREFIX = 'google/protobuf/'
_PROTO_IMPORT_RE = re.compile(
    r'^\s*import\s+(?:public\s+|weak\s+)?"([^"]+)"\s*;', re.MULTILINE)

# ── 符号表枚举（INT-1952：上传端点回吐 service / method / 字段，A3 前端消费）──
#: 字段展开深度：顶层 + 一层嵌套（再深由前端按类型名自行展示）
SYMBOL_MAX_FIELD_DEPTH = 2
#: well-known types 只给类型名不展开
_WELL_KNOWN_TYPE_PREFIX = 'google.protobuf.'
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
        self._file_set = None

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

    # ── 符号表枚举（只读；INT-1952 上传端点 / A3 前端下拉与类型预览）──

    @property
    def file_set(self):
        """编译产物 FileDescriptorSet（与 pool 同一份字节，只解析一次）。"""
        if self._file_set is None:
            from google.protobuf import descriptor_pb2

            file_set = descriptor_pb2.FileDescriptorSet()
            file_set.ParseFromString(self._descriptor_set_bytes)
            self._file_set = file_set
        return self._file_set

    def iter_services(self):
        """按声明顺序产出 ServiceDescriptor（含 import 进来的文件，通常无 service）。"""
        for file_proto in self.file_set.file:
            package = file_proto.package
            for service_proto in file_proto.service:
                full_name = (f'{package}.{service_proto.name}'
                             if package else service_proto.name)
                try:
                    yield self.pool.FindServiceByName(full_name)
                except KeyError:
                    logger.debug('service 未进 descriptor pool: %s',
                                 full_name, exc_info=True)

    def enumerate_services(self) -> List[Dict[str, Any]]:
        """回吐可执行符号表：service → method → 输入 / 输出字段。

        规则（INT-1952 卡面 §5 第 5 条，前端直接消费，不另解析一套）：
        - **client-streaming-only 方法剔除**：执行期只支持 unary / server_stream /
          bidi，吐出去前端下拉必然报错；`method_kind` 仍只用 `METHOD_KINDS` 三值。
        - `input_type` / `output_type` 写 descriptor 全限定名（与
          `meta.grpc.service` 全名口径一致）。
        - 字段展开到 `SYMBOL_MAX_FIELD_DEPTH` 层（顶层 + 一层嵌套），`path` 用
          点号；map 写完整 `map<k, v>`；enum 写枚举全名不展开；
          `google.protobuf.*` 只给类型名不展开；自引用 / 递归在重复出现处截断。
        """
        services: List[Dict[str, Any]] = []
        for service_desc in self.iter_services():
            methods: List[Dict[str, Any]] = []
            for method_desc in service_desc.methods:
                kind = _method_kind_of(method_desc)
                if kind is None:  # client-streaming-only：执行期不支持
                    continue
                methods.append({
                    'name': method_desc.name,
                    'method_kind': kind,
                    'input_type': method_desc.input_type.full_name,
                    'output_type': method_desc.output_type.full_name,
                    'input_fields': describe_message_fields(method_desc.input_type),
                    'output_fields': describe_message_fields(method_desc.output_type),
                })
            services.append({'name': service_desc.full_name, 'methods': methods})
        return services


# ── 符号表枚举的纯函数（CompiledProto 内部复用，也可独立单测）────────────

def _method_kind_of(method_desc) -> Optional[str]:
    """(client_streaming, server_streaming) → METHOD_KINDS 的键；不支持则 None。"""
    flags = (method_desc.client_streaming, method_desc.server_streaming)
    return next((name for name, kinds in METHOD_KINDS.items() if kinds == flags),
                None)


def _is_map_field(field_desc) -> bool:
    """proto3 map 字段在 descriptor 里是 `map_entry=True` 的合成 message。"""
    message_desc = field_desc.message_type
    return message_desc is not None and message_desc.GetOptions().map_entry


def _field_type_label(field_desc) -> str:
    """字段的类型标签：标量 / 全限定消息名 / 全限定枚举名 / map<k, v>。"""
    if field_desc.message_type is not None:
        if _is_map_field(field_desc):
            entry_desc = field_desc.message_type
            key_label = _field_type_label(entry_desc.fields_by_name['key'])
            value_label = _field_type_label(entry_desc.fields_by_name['value'])
            return f'map<{key_label}, {value_label}>'
        return field_desc.message_type.full_name
    if field_desc.enum_type is not None:
        return field_desc.enum_type.full_name
    from google.protobuf.descriptor_pb2 import FieldDescriptorProto

    return FieldDescriptorProto.Type.Name(field_desc.type) \
        .replace('TYPE_', '').lower()


def _expandable_message(field_desc, ancestors, depth_left):
    """该字段的嵌套 message 是否继续展开（深度 / well-known / 递归三重限制）。"""
    if depth_left <= 1:
        return None
    message_desc = field_desc.message_type
    if message_desc is None or _is_map_field(field_desc):
        return None
    if message_desc.full_name.startswith(_WELL_KNOWN_TYPE_PREFIX):
        return None
    if message_desc.full_name in ancestors:
        return None
    return message_desc


def _expand_fields(message_desc, prefix, depth_left, ancestors, out) -> None:
    for field_desc in message_desc.fields:
        path = f'{prefix}.{field_desc.name}' if prefix else field_desc.name
        out.append({
            'path': path,
            'type': _field_type_label(field_desc),
            # map 自带键值语义，不算 repeated
            'repeated': bool(field_desc.is_repeated) and not _is_map_field(field_desc),
        })
        nested = _expandable_message(field_desc, ancestors, depth_left)
        if nested is not None:
            _expand_fields(nested, path, depth_left - 1,
                           ancestors | {nested.full_name}, out)


def describe_message_fields(message_desc) -> List[Dict[str, Any]]:
    """展开一个消息的字段为 `[{path, type, repeated}]`（最多两层）。"""
    out: List[Dict[str, Any]] = []
    _expand_fields(message_desc, '', SYMBOL_MAX_FIELD_DEPTH,
                   frozenset({message_desc.full_name}), out)
    return out


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


def parse_request_or_config(payload: dict, method: GrpcMethod):
    """调用侧包装：请求体与 proto 不符 → `GrpcProtoError`（config / 400）。

    `json_format.ParseError` 的 MRO 是 `ParseError → Error → Exception`，不是
    `ValueError`，直接外抛会被执行器当未捕获异常（用例崩掉而不是判配置错误）。
    多余字段 / 类型不符都是 `body_template` 与 proto 不一致，属配置类。
    """
    from google.protobuf.json_format import ParseError

    try:
        return parse_request(payload, method)
    except ParseError as exc:
        raise GrpcProtoError(f"请求体与 proto 不符: {exc}")


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


def _normalize_target(target: str) -> str:
    """把带 scheme 的 endpoint 归一为 gRPC target（host:port）。

    写侧接口地址校验只允许 http/https/ws/wss 协议前缀（对外展示口径），
    而 grpc.insecure_channel 只接受 host:port / dns:///host:port。
    带 scheme 的写法在这里剥成 netloc，否则 gRPC 会把它当未知 resolver 挂死。
    """
    raw = str(target or '').strip()
    if '://' not in raw:
        return raw
    from urllib.parse import urlsplit
    parts = urlsplit(raw)
    return parts.netloc or raw


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
        self.target = _normalize_target(target)
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

        `_ready` 只在首次探测成功后置位（channel 属本客户端、用例内复用）；
        目标中途重启不会重探，后续调用按 UNAVAILABLE 等 status 分类兜底
        （只是可观测性略差，不影响错误归类结果）。
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
        request = parse_request_or_config(payload, self.method)
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
        request = parse_request_or_config(payload, self.method)
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
        self._send_queue.put(parse_request_or_config(payload, self._client.method))

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

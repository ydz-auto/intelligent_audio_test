# -*- coding: utf-8 -*-
"""被测 API `meta.grpc` 契约常量与校验（INT-1953 / A3 后端对齐）。

写侧（`application/api_crud_service.py`）与执行侧（`infrastructure/adapters/
grpc_adapter.py`、`…/transport/grpc_client.py`）共用本模块的常量与校验口径：
同一份词表、同一个 proto 体积上限、同一套凭据保留判断，不各写一份字面量
（A0 §3.5 / A1 §四：`meta.grpc` 未新增配置键）。

纯逻辑、无 IO：读侧掩码与写侧合并都返回新 dict，不修改入参。
"""
from __future__ import annotations

import re
from typing import Dict, Optional

# proto 单文件体积上限（A0 §3.5③：256 KB）。源头在 shared/：api_gateway 不
# import api_test_service，网关侧预检（INT-1952）与本域必须同一份字面量。
from shared.models.proto_limits import PROTO_MAX_BYTES

# method_kind → (client_streaming, server_streaming)。表外取值写侧 400。
METHOD_KINDS = {
    'unary': (False, False),
    'server_stream': (False, True),
    'bidi': (True, True),
}
GRPC_METHOD_KINDS = tuple(METHOD_KINDS)

# proto_sha256 声明格式：64 位小写十六进制
PROTO_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')

# meta.grpc 必填键（缺哪个报哪个）
GRPC_META_REQUIRED_KEYS = ('proto_object_key', 'service', 'method', 'method_kind')

# meta.grpc 词表（A1 §四 config 键 + reflection 开关）；表外未知键写侧 400，
# 与 meta.sse 的「未知键 400」同口径
GRPC_META_KNOWN_KEYS = frozenset({
    'proto_object_key', 'proto_sha256', 'proto_size',
    'service', 'method', 'method_kind',
    'metadata', 'deadline_ms', 'reflection',
})

# metadata 敏感键（大小写不敏感，`-` / `_` 等价，与 shared.utils.secret_mask
# 的键名归一同口径）。值读出时掩码、写回时按掩码保留库里原值。
GRPC_SENSITIVE_METADATA_KEYS = frozenset({
    'authorization', 'proxy_authorization', 'x_api_key', 'api_key',
    'apikey', 'token', 'x_auth_token',
})

# 凭据固定掩码（与 shared.utils.secret_mask 的 _MASK 同值，零明文）
CREDENTIAL_MASK = '****'

_GRPC_PROTOCOL = 'grpc'


def _normalize_key(key) -> str:
    return str(key).strip().strip('"\'').lower().replace('-', '_')


def is_sensitive_metadata_key(key) -> bool:
    """metadata 键是否承载凭据（大小写不敏感，`-` / `_` 等价）。"""
    return _normalize_key(key) in GRPC_SENSITIVE_METADATA_KEYS


def _is_int(value) -> bool:
    """严格整数判定：bool 是 int 子类，不得当整数放行。"""
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_metadata_block(metadata) -> Optional[str]:
    """metadata 形状校验：对象、键已小写、值不含 CR/LF（与执行侧同口径）。"""
    if not isinstance(metadata, dict):
        return "meta.grpc.metadata 必须是一个 JSON 对象"
    for key, value in metadata.items():
        name = str(key)
        if name != name.lower():
            return f"meta.grpc.metadata 的键必须小写: {name!r}"
        text = '' if value is None else str(value)
        if '\r' in text or '\n' in text:
            return f"meta.grpc.metadata[{name!r}] 的值不得包含 CR/LF"
    return None


def validate_grpc_meta(meta, protocol=None) -> Optional[str]:
    """校验 `meta.grpc`（INT-1953 §2.2）。

    **存在即校验**：不按 `protocol` 决定是否校验——前端切协议时会把旧协议的
    子对象留在 meta 里，按协议跳过校验会让脏配置一路存到执行期。`protocol`
    只用于这一条存在性约束：`protocol == 'grpc'` 且缺 `meta.grpc` → 400。

    Args:
        meta: 完整 meta dict（或其缺失时的 None）
        protocol: 归一后的规范协议值（http/websocket/sse/grpc）或 None

    Returns:
        错误文案（写侧 400 用）或 None。
    """
    if not isinstance(meta, dict):
        # meta 整体形状由 _validate_api_data 统一把口；执行侧（适配器）拿到的
        # 非 dict meta 视为缺失，同样按存在性约束拒绝
        if protocol == _GRPC_PROTOCOL:
            return ("gRPC API 必须配置 meta.grpc"
                    "（proto_object_key / service / method / method_kind）")
        return None

    cfg = meta.get('grpc')
    if cfg is None:
        if protocol == _GRPC_PROTOCOL:
            return ("gRPC API 必须配置 meta.grpc"
                    "（proto_object_key / service / method / method_kind）")
        return None
    if not isinstance(cfg, dict):
        return "meta.grpc 必须是一个 JSON 对象"

    missing = [k for k in GRPC_META_REQUIRED_KEYS if not cfg.get(k)]
    if missing:
        return f"meta.grpc 缺少必填键: {', '.join(missing)}"

    if cfg.get('reflection'):
        return "meta.grpc.reflection 本轮固定 false——server reflection 未实现"

    method_kind = str(cfg.get('method_kind')).strip().lower()
    if method_kind not in GRPC_METHOD_KINDS:
        return (f"meta.grpc.method_kind 非法: {cfg.get('method_kind')!r}"
                f"（合法值: {' / '.join(GRPC_METHOD_KINDS)}）")

    deadline = cfg.get('deadline_ms')
    if deadline is not None and (not _is_int(deadline) or deadline <= 0):
        return f"meta.grpc.deadline_ms 必须为正整数: {deadline!r}"

    if cfg.get('metadata') is not None:
        error = _validate_metadata_block(cfg.get('metadata'))
        if error:
            return error

    proto_size = cfg.get('proto_size')
    if proto_size is not None and (not _is_int(proto_size)
                                   or not 1 <= proto_size <= PROTO_MAX_BYTES):
        return f"meta.grpc.proto_size 必须在 1-{PROTO_MAX_BYTES} 之间: {proto_size!r}"

    proto_sha = cfg.get('proto_sha256')
    if proto_sha is not None and str(proto_sha).strip():
        if not isinstance(proto_sha, str) or not PROTO_SHA256_RE.match(proto_sha):
            return "meta.grpc.proto_sha256 必须为 64 位小写十六进制字符串"

    unknown = sorted(str(k) for k in cfg if k not in GRPC_META_KNOWN_KEYS)
    if unknown:
        return (f"meta.grpc 存在未知键: {', '.join(unknown)}"
                f"（仅支持: {', '.join(sorted(GRPC_META_KNOWN_KEYS))}）")

    return None


def redact_grpc_meta_credentials(meta) -> Dict:
    """读侧脱敏：`meta.grpc.metadata` 的敏感键值替换为固定掩码。

    `meta.grpc` 原先整体原样透传，`metadata.authorization` 等凭据对所有具备
    `api_config:read` 的用户可见——与 `meta.api_keys` 零响应口径不一致。本函数
    只动敏感键；`x-request-id` 等非敏感键行为不变。返回新 dict，不修改入参。
    """
    if not isinstance(meta, dict):
        return meta
    grpc_cfg = meta.get('grpc')
    if not isinstance(grpc_cfg, dict):
        return meta
    metadata = grpc_cfg.get('metadata')
    if not isinstance(metadata, dict) or not metadata:
        return meta

    masked = {}
    changed = False
    for key, value in metadata.items():
        if is_sensitive_metadata_key(key) and value:
            masked[key] = CREDENTIAL_MASK
            changed = True
        else:
            masked[key] = value
    if not changed:
        return meta
    out = dict(meta)
    out['grpc'] = {**grpc_cfg, 'metadata': masked}
    return out


def merge_grpc_metadata_credentials(incoming_meta, stored_meta) -> Dict:
    """写侧保留语义：敏感键回传掩码时保留库里原值（同 `meta.api_keys` 的 D2 口径）。

    - 入参值 == 掩码 `****` → 保留库里原值（读侧拿不到明文，整块覆盖会静默
      清空凭据）；库里没有该键时直接丢弃，不把掩码字面量落库。
    - 显式传新值 → 覆盖。
    - 显式传空串 → 删除该键（清空语义）。

    非敏感键与非 `metadata` 内容一律原样透传；未发生替换时返回入参本身。
    """
    if not isinstance(incoming_meta, dict):
        return incoming_meta
    grpc_cfg = incoming_meta.get('grpc')
    if not isinstance(grpc_cfg, dict):
        return incoming_meta
    metadata = grpc_cfg.get('metadata')
    if not isinstance(metadata, dict):
        return incoming_meta

    stored_metadata = {}
    if isinstance(stored_meta, dict):
        stored_grpc = stored_meta.get('grpc')
        if isinstance(stored_grpc, dict) and isinstance(stored_grpc.get('metadata'), dict):
            stored_metadata = stored_grpc['metadata']

    merged = {}
    changed = False
    for key, value in metadata.items():
        if is_sensitive_metadata_key(key):
            if value == CREDENTIAL_MASK:
                changed = True
                if key in stored_metadata:
                    merged[key] = stored_metadata[key]
                continue
            if value == '':
                changed = True
                continue
        merged[key] = value

    if not changed:
        return incoming_meta
    out = dict(incoming_meta)
    out['grpc'] = {**grpc_cfg, 'metadata': merged}
    return out


__all__ = [
    'METHOD_KINDS',
    'GRPC_METHOD_KINDS',
    'PROTO_MAX_BYTES',
    'PROTO_SHA256_RE',
    'GRPC_META_REQUIRED_KEYS',
    'GRPC_META_KNOWN_KEYS',
    'GRPC_SENSITIVE_METADATA_KEYS',
    'CREDENTIAL_MASK',
    'is_sensitive_metadata_key',
    'validate_grpc_meta',
    'redact_grpc_meta_credentials',
    'merge_grpc_metadata_credentials',
]

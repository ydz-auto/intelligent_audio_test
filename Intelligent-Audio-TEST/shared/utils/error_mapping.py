# -*- coding: utf-8 -*-
"""被测 API 协议错误码归一（INT-1789 / A1，承 A0 裁定 §3.6）。

所有协议的原始错误码归一到一个 `biz_code` 词表（`{0} ∪ 语义化 HTTP 状态码`）
+ 两个诊断字段：

- `error_source`：`http` / `websocket` / `sse` / `grpc` / `network` / `config`
- `raw_code`：协议原始码（HTTP status / WS close code / gRPC status int）——
  只作诊断，**不进业务字段**。

本模块只落 gRPC 一张表（A1 范围）；HTTP / WS 的映射已在各适配器内实现
（INT-1770 起的 `error_code_mapping` 契约不变），A2（SSE）落地时在此补表。
执行侧既有判定 `biz_code in [400, 404]` 与 `str(biz_code) != '0'` 在本表下
语义不变，不需要改写。
"""
from typing import Dict, Tuple

# error_source 词表（A0 §3.6）
ERROR_SOURCE_HTTP = 'http'
ERROR_SOURCE_WEBSOCKET = 'websocket'
ERROR_SOURCE_SSE = 'sse'
ERROR_SOURCE_GRPC = 'grpc'
ERROR_SOURCE_NETWORK = 'network'
ERROR_SOURCE_CONFIG = 'config'

# gRPC 状态码 → (biz_code, biz_msg)；逐条对齐 A0 §3.6 映射表。
# 0 = OK 表示成功（biz_code=0）。表外状态码不静默兜底：`grpc_status_to_biz`
# 抛 KeyError，调用方必须显式登记后才可用（见 `UNMAPPED_STATUS_BIZ` 兜底开关）。
GRPC_STATUS_TO_BIZ: Dict[int, Tuple[int, str]] = {
    0: (0, 'OK'),
    1: (499, 'CANCELLED'),
    2: (500, 'UNKNOWN'),
    3: (400, 'INVALID_ARGUMENT'),
    4: (504, 'DEADLINE_EXCEEDED'),
    5: (404, 'NOT_FOUND'),
    6: (409, 'ALREADY_EXISTS'),
    7: (403, 'PERMISSION_DENIED'),
    8: (429, 'RESOURCE_EXHAUSTED'),
    9: (412, 'FAILED_PRECONDITION'),
    10: (409, 'ABORTED'),
    # A0 §3.6 表未单列 OUT_OF_RANGE：语义上是「参数超出可接受范围」，与
    # INVALID_ARGUMENT 同类，显式登记为 400（非默认兜底）。
    11: (400, 'OUT_OF_RANGE'),
    12: (501, 'UNIMPLEMENTED'),
    13: (500, 'INTERNAL'),
    14: (503, 'UNAVAILABLE'),
    15: (500, 'DATA_LOSS'),
    16: (401, 'UNAUTHENTICATED'),
}

# 表外状态码的显式兜底：归类 500 并保留原始码，记 WARNING（部署了新版 gRPC
# 引入新状态码时不至于把调用打成未知异常）。
UNMAPPED_STATUS_BIZ = (500, 'UNKNOWN_STATUS')


def grpc_status_to_biz(status_code: int) -> Tuple[int, str]:
    """gRPC status int → (biz_code, biz_msg)。"""
    key = int(status_code)
    return GRPC_STATUS_TO_BIZ.get(key, UNMAPPED_STATUS_BIZ)


def grpc_error_fields(status_code: int) -> Dict[str, object]:
    """gRPC 失败 → 归一错误字段（纯增键，现有消费者忽略未知键）。

    `biz_msg` 用 status 名（A0 表口径），不把原始协议文本塞进业务字段。
    """
    biz_code, biz_msg = grpc_status_to_biz(status_code)
    return {
        'biz_code': biz_code,
        'biz_msg': biz_msg,
        'error_source': ERROR_SOURCE_GRPC,
        'raw_code': int(status_code),
    }


def config_error_fields(reason: str) -> Dict[str, object]:
    """配置错误（proto 缺失 / 方法不存在 / method_kind 不符 / 超限）→ 400。"""
    return {
        'biz_code': 400,
        'biz_msg': reason,
        'error_source': ERROR_SOURCE_CONFIG,
        'raw_code': None,
    }


def network_error_fields(reason: str) -> Dict[str, object]:
    """网络层错误（DNS / 连接拒绝 / TLS）→ 503。"""
    return {
        'biz_code': 503,
        'biz_msg': reason,
        'error_source': ERROR_SOURCE_NETWORK,
        'raw_code': None,
    }


def is_success_biz_code(biz_code) -> bool:
    """业务码是否表示成功（`None` 视为未取到业务码，不等于成功）。"""
    return biz_code is not None and str(biz_code) == '0'

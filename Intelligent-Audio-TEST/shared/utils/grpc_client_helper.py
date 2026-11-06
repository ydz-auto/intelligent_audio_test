# -*- coding: utf-8 -*-
"""gRPC 客户端统一调用工具

提供通用调用函数，消除 shared/clients/grpc_clients.py 和
report_service/infrastructure/clients/grpc_clients.py 中 45+ 个
便捷封装函数重复的 8 行模板，并统一两套相反的失败语义。

使用前（两套相反语义）::

    # shared/clients — 失败时 raise RuntimeError
    def submit_evaluate_case(...):
        stub = get_evaluation_service_stub()
        resp = stub.EvaluateCase(req)
        if not resp.success:
            raise RuntimeError(f"EvaluateCase gRPC 失败: {resp.message}")
        return json.loads(resp.data) if resp.data else {}

    # report_service — 失败时静默返回空集合
    def _grpc_get_task_devices(task_id):
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTaskDevices(req)
            if not resp.success:
                return []
            return _loads(resp.data, [])
        except Exception:
            return []

使用后（统一）::

    from shared.utils.grpc_client_helper import call_rpc

    # 失败时抛异常（默认）
    result = call_rpc(stub, 'EvaluateCase', eval_pb.EvaluateCaseRequest(...))

    # 失败时返回默认值（兼容旧 report_service 风格）
    devices = call_rpc(
        stub, 'GetTaskDevices', task_pb.GetTaskDevicesRequest(task_id=tid),
        default=[], raise_on_failure=False,
    )
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from shared.utils.grpc_json import loads as _loads, dumps as _dumps

logger = logging.getLogger(__name__)


def call_rpc(
    stub,
    method_name: str,
    request,
    *,
    default: Any = None,
    raise_on_failure: bool = True,
    parse_data: bool = True,
):
    """通用 gRPC 客户端调用函数。

    统一封装 stub 调用 → resp.success 检查 → resp.data 解析的 8 行模板。

    Args:
        stub: gRPC stub 实例
        method_name: RPC 方法名（如 'EvaluateCase'）
        request: proto 请求对象
        default: 失败时返回的默认值（仅 raise_on_failure=False 时生效）
        raise_on_failure: 失败时是否抛异常。
            True（默认）— resp.success=False 时 raise RuntimeError，
            统一 shared/clients 语义。
            False — 返回 default，兼容 report_service 旧语义。
        parse_data: 是否自动 JSON 解析 resp.data。
            True（默认）— 返回 ``_loads(resp.data, default)``。
            False — 返回原始 resp。

    Returns:
        解析后的数据（parse_data=True）或原始响应（parse_data=False）。
        失败时根据 raise_on_failure 决定抛异常或返回 default。

    Raises:
        RuntimeError: 当 resp.success=False 且 raise_on_failure=True 时。
    """
    try:
        method = getattr(stub, method_name)
        resp = method(request)
        if not resp.success:
            msg = f"{method_name} gRPC 失败: {resp.message}"
            if raise_on_failure:
                raise RuntimeError(msg)
            logger.warning(msg)
            return default
        if not parse_data:
            return resp
        if not resp.data:
            return default
        return _loads(resp.data, default)
    except RuntimeError:
        raise
    except Exception as e:
        logger.error("%s gRPC 调用异常: %s", method_name, e, exc_info=True)
        if raise_on_failure:
            raise
        return default


def call_rpc_with_data(
    stub,
    method_name: str,
    data: dict,
    request_cls,
    *,
    default: Any = None,
    raise_on_failure: bool = True,
):
    """通用 gRPC 调用（data 字段版本）。

    很多 RPC 方法只有一个 ``data`` JSON 字段，本函数自动构造请求。

    Args:
        stub: gRPC stub 实例
        method_name: RPC 方法名
        data: 要序列化为 request.data 的字典
        request_cls: proto 请求类
        default: 失败时返回的默认值
        raise_on_failure: 失败时是否抛异常

    Returns:
        解析后的数据，或 default

    用法::

        result = call_rpc_with_data(
            stub, 'CreateDevice', payload, e2e_pb.CreateDeviceRequest,
            default={},
        )
    """
    request = request_cls(data=_dumps(data))
    return call_rpc(stub, method_name, request,
                    default=default, raise_on_failure=raise_on_failure)


# ------------------------------------------------------------------
# 批量查询辅助（消除 N+1 循环模板）
# ------------------------------------------------------------------

def call_rpc_batch_by_ids(
    get_stub_fn,
    method_name: str,
    ids: list,
    request_cls,
    id_field: str = 'ids',
    *,
    default: Any = None,
    raise_on_failure: bool = False,
) -> dict:
    """批量按 ID 查询，返回 {id: item} 映射。

    消除 report_service 中 3 处 ``_grpc_get_xxx_by_ids`` 循环模板。

    注意：此函数要求 RPC 方法接受 id 列表参数并返回包含完整列表的响应。
    如果服务端不支持批量查询，应改为循环调用。

    Args:
        get_stub_fn: 返回 stub 的无参函数（如 ``get_device_config_service_stub``）
        method_name: RPC 方法名（如 'GetDevicesByIds'）
        ids: 待查询的 ID 列表
        request_cls: proto 请求类
        id_field: 请求中 ID 列表的字段名（默认 'ids'）
        default: 失败时返回的默认值
        raise_on_failure: 失败时是否抛异常

    Returns:
        {id: item_dict} 映射，失败时返回空 dict
    """
    if not ids:
        return {}
    stub = get_stub_fn()
    kwargs = {id_field: list(ids)}
    request = request_cls(**kwargs)
    result = call_rpc(stub, method_name, request,
                      default=default, raise_on_failure=raise_on_failure)
    if not result:
        return {}
    # 支持列表或 dict 响应
    if isinstance(result, list):
        return {int(item.get('id')): item for item in result if item.get('id')}
    if isinstance(result, dict):
        items = result.get('items', result.get('data', []))
        if isinstance(items, list):
            return {int(item.get('id')): item for item in items if item.get('id')}
    return {}

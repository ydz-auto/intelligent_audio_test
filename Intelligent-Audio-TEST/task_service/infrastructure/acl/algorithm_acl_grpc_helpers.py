# -*- coding: utf-8 -*-
"""算法 ACL gRPC 响应解析辅助函数模块。

从 algorithm_acl_repository.py 抽取的共享底层辅助，供主仓储与各 Mixin 复用，
避免主文件与 Mixin 之间的循环导入：
- _get_stub / _group_stub: gRPC stub 便捷获取
- _items / _one: 响应数据提取（可选 DTO 包装）
- _raise_on_failure: 写操作统一失败处理
"""
from __future__ import annotations

from shared.clients.grpc_clients import (
    get_algorithm_definition_service_stub,
    get_algorithm_group_service_stub,
)
from shared.utils.grpc_json import loads as _loads
from shared.utils.dto_utils import dict_to_dto, dict_list_to_dto


def _get_stub():
    """获取 AlgorithmDefinitionService gRPC stub（便捷封装）。"""
    return get_algorithm_definition_service_stub()


def _group_stub():
    """获取 AlgorithmGroupService gRPC stub（便捷封装）。"""
    return get_algorithm_group_service_stub()


def _items(resp, key: str = "items", dto_cls=None) -> list:
    """从列表型 gRPC 响应中提取条目列表，可选包装为 DTO。

    兼容 servicer 返回的 {"items": [...]} / {"parameters": [...]} /
    {"mappings": [...]} / {"relations": [...]} 等不同键名。
    """
    if not resp.success:
        raise RuntimeError(resp.message)
    payload = _loads(resp.data, None)
    if not payload:
        return []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = None
        for candidate in (key, "parameters", "mappings", "relations", "params"):
            items = payload.get(candidate)
            if isinstance(items, list):
                break
        if items is None:
            return []
    else:
        return []
    if dto_cls is not None:
        return dict_list_to_dto(items, dto_cls)
    return items


def _one(resp, dto_cls=None):
    """从单条查询 gRPC 响应中提取 dict/DTO，无数据返回 None。"""
    if not resp.success:
        return None
    if not resp.data:
        return None
    payload = _loads(resp.data, None)
    if not payload:
        return None
    if not isinstance(payload, dict):
        return None
    if dto_cls is not None:
        return dict_to_dto(payload, dto_cls)
    return payload


def _raise_on_failure(resp):
    """写操作统一失败处理：success=False 即抛 RuntimeError。"""
    if not resp.success:
        raise RuntimeError(resp.message or "algorithm_service gRPC 调用失败")

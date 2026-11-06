# -*- coding: utf-8 -*-
"""共享 DTO 工具：dict → dataclass 转换。

提供 ``dict_to_dto`` / ``dict_list_to_dto`` 两个函数，
被各微服务 ACL 仓储复用，避免在每个服务重复实现。
"""
from __future__ import annotations

from dataclasses import dataclass, fields as _dc_fields
from typing import List, Optional, Type, TypeVar, Union

T = TypeVar("T")


def dict_to_dto(data: Optional[dict], dto_cls: Type[T]) -> Optional[T]:
    """将单个 dict 转换为 dataclass DTO，data 为 None/非 dict 时返回 None。"""
    if data is None or not isinstance(data, dict):
        return None
    valid = {f.name for f in _dc_fields(dto_cls)}
    return dto_cls(**{k: v for k, v in data.items() if k in valid})


def dict_list_to_dto(data: Optional[Union[list, dict]], dto_cls: Type[T],
                     list_key: Optional[str] = None) -> List[T]:
    """将 list[dict] 转换为 List[dataclass DTO]。

    若 data 为 dict 且提供了 list_key，则从 data[list_key] 提取列表。
    """
    if data is None:
        return []
    if isinstance(data, dict):
        if list_key and isinstance(data.get(list_key), list):
            data = data[list_key]
        else:
            return []
    if not isinstance(data, list):
        return []
    valid = {f.name for f in _dc_fields(dto_cls)}
    return [dto_cls(**{k: v for k, v in d.items() if k in valid})
            for d in data if isinstance(d, dict)]


def get_id_from(obj) -> Optional[int]:
    """从 dict 或 dataclass 对象提取 id 字段，兼容 dict/DTO 两种入参。"""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get('id')
    return getattr(obj, 'id', None)


def dto_to_dict(dto) -> Optional[dict]:
    """将 dataclass DTO 转换回 dict，若含 result_data 字段则合并到顶层。

    与 dict_to_dto 互逆：先 asdict 展开，再把 result_data 中的动态键提升到顶层。
    非 dataclass 入参（dict / None）直接返回。
    """
    if dto is None:
        return None
    if isinstance(dto, dict):
        return dto
    if not hasattr(dto, '__dataclass_fields__'):
        return dto
    d = {f.name: getattr(dto, f.name) for f in _dc_fields(type(dto))}
    result_data = d.pop('result_data', None)
    if isinstance(result_data, dict):
        d.update(result_data)
    return d

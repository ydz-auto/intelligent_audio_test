# -*- coding: utf-8 -*-
"""AlgorithmDefinitionServicer 的公共工具与基础 mixin。

从 _param_mixin.py 拆分（现位于 mixins/ 子包），提供：
- _success / _failure：构造 AlgorithmResponse 的模块级工具函数
- _normalize_dimension_param_data：evaluation_dimension_params 写侧数值/布尔字段归一
- _ParamBaseMixin：提供写操作后刷新缓存的能力，供各子 mixin 继承
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

import logging

from shared.proto import algorithm_service_pb2 as _pb
from shared.utils.grpc_json import dumps as _dumps

logger = logging.getLogger(__name__)


# evaluation_dimension_params 中非文本列（INT-1683）：
# 空串直接下传会让数据库抛 invalid input syntax，整条参数被丢弃而调用方仍拿到成功。
_INT_FIELDS = ("ui_order",)
_FLOAT_FIELDS = ("pass_threshold",)
_BOOL_FIELDS = ("visible_in_report", "required")


def _normalize_int(value: Any, field: str) -> Any:
    """整数字段归一：空串 → None；可解析值 → int；其余抛 ValueError。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"字段 {field} 需要整数，收到 {value!r}")
    # JSON 里的 3.0 视为 3；有小数部分的值不静默截断
    if not number.is_integer():
        raise ValueError(f"字段 {field} 需要整数，收到 {value!r}")
    return int(number)


def _normalize_float(value: Any, field: str) -> Any:
    """浮点字段归一：空串 → None；可解析值 → float；其余抛 ValueError。"""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"字段 {field} 需要数值，收到 {value!r}")


def _normalize_bool(value: Any, field: str) -> Any:
    """布尔字段归一：空串 → None；可解析值 → bool；其余抛 ValueError。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return None
        if text in ("true", "1"):
            return True
        if text in ("false", "0"):
            return False
    raise ValueError(f"字段 {field} 需要布尔值，收到 {value!r}")


def _normalize_dimension_param_data(data: dict) -> dict:
    """归一 evaluation_dimension_params 写侧入参（INT-1683）。

    空串（前端空表单 / 脚本直接透传）统一归一为 NULL，与前端
    ``toNullableNumber('') → null`` 口径一致，避免数据库解析失败导致
    整条参数被静默丢弃；非空非法值直接抛 ValueError，让调用方拿到
    明确失败而不是写进一份缺字段的数据。

    覆盖该表全部非文本列（int / float / bool），不只是 pass_threshold。
    """
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    for field in _INT_FIELDS:
        if field in normalized:
            normalized[field] = _normalize_int(normalized[field], field)
    for field in _FLOAT_FIELDS:
        if field in normalized:
            normalized[field] = _normalize_float(normalized[field], field)
    for field in _BOOL_FIELDS:
        if field in normalized:
            normalized[field] = _normalize_bool(normalized[field], field)
    return normalized


def _success(data: Any = None, message: str = "ok"):
    """构造成功响应（AlgorithmResponse）。"""
    return _pb.AlgorithmResponse(
        success=True,
        message=message,
        data=_dumps(data) if data is not None else "",
    )


def _failure(message: str, data: Any = None):
    """构造失败响应（AlgorithmResponse）。"""
    return _pb.AlgorithmResponse(
        success=False,
        message=message,
        data=_dumps(data) if data is not None else "",
    )


class _ParamBaseMixin:
    """参数方法基础 mixin，仅提供写操作后的缓存刷新能力。

    各子 mixin（CRUD/映射/维度关系/算法定义）继承本类，从而获得
    ``self._invalidate_cache``；最终由 ``_ParamMethodsMixin`` 多重继承聚合。
    """

    @staticmethod
    def _invalidate_cache(
        algorithm_types: Optional[Iterable[str]] = None,
        dimension_ids: Optional[Iterable[int]] = None,
    ):
        """写操作后刷新缓存（按受影响切片重载 L1 + Redis pubsub 通知其他进程）。

        INT-1666：能确定受影响范围的写操作只重载对应切片
        （单个 algorithm_type / 单个 dimension_id），避免每次写都全量
        重建整份算法配置快照；范围未知时不传参 → 全量重载。
        """
        try:
            from algorithm_service.infrastructure.persistence.config_cache import get_config_cache
            get_config_cache().invalidate(
                algorithm_types=algorithm_types, dimension_ids=dimension_ids)
        except Exception:
            logger.exception("刷新缓存失败（_invalidate_cache）")

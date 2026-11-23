# -*- coding: utf-8 -*-
"""数值归一工具（聚合口径统一入口）。

聚合时只允许丢弃真正的缺失值（None/空串/无法转换）与非有限值（NaN/Inf），
合法的 0 必须保留；否则 WER=0、混淆率=0 这类合法 0 分会被当成缺失值丢掉，
导致平均值虚高。
"""
import math
from typing import Any, Optional


def to_finite_float(value: Any) -> Optional[float]:
    """转为有限 float；None / 空串 / NaN / Inf / 不可转 → None。"""
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None

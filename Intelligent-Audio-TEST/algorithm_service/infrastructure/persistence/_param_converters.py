# -*- coding: utf-8 -*-
"""参数仓储 PO ↔ dict 转换层。

从 param_repository.py 拆分而来（原文件过大，按职责拆分为多个实现模块）：
- _po_to_dict: PO 序列化为 dict（优先调用 po.to_dict()，否则遍历 __table__.columns）
- _resolve_param_model: 按 param_type_source（device/api）解析目标 PO 类
"""
from __future__ import annotations

from typing import Dict, Any

from shared.utils.camel_case import camel_to_snake

from algorithm_service.infrastructure.persistence.models import (
    AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    AlgorithmApiParam as AlgorithmApiParamPO,
)


# ========== 辅助函数 ==========

def _apply_update_fields(po, fields: Dict[str, Any]) -> None:
    """将待更新字段应用到 PO。

    - None 值跳过
    - 键名兼容 camelCase（网关 update_param 原样透传请求体，如 paramName → param_name）
    - PO 上不存在的字段忽略，避免 setattr 到非映射属性造成静默 no-op
    """
    for field, value in fields.items():
        if value is None:
            continue
        if not hasattr(po, field):
            field = camel_to_snake(field)
        if hasattr(po, field):
            setattr(po, field, value)

def _po_to_dict(po) -> Dict[str, Any]:
    """将 PO 序列化为 dict（优先调用 PO.to_dict）。

    与 servicers.py 中的 _po_to_dict 行为一致：
    - 优先调用 po.to_dict()
    - 否则遍历 __table__.columns 生成 {name: value}
    """
    if po is None:
        return None  # type: ignore[return-value]
    if hasattr(po, "to_dict"):
        return po.to_dict()
    return {
        c.name: getattr(po, c.name, None)
        for c in po.__table__.columns
    }


def _resolve_param_model(param_type_source: str):
    """根据 param_type_source 解析目标 PO 类。

    - "api" → AlgorithmApiParamPO
    - 其他（默认 device / 未指定）→ AlgorithmDeviceParamPO
    """
    if param_type_source == "api":
        return AlgorithmApiParamPO
    return AlgorithmDeviceParamPO

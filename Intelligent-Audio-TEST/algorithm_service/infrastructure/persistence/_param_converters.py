# -*- coding: utf-8 -*-
"""参数仓储 PO ↔ dict 转换层。

从 param_repository.py 拆分而来（原文件过大，按职责拆分为多个实现模块）：
- _po_to_dict: PO 序列化为 dict（优先调用 po.to_dict()，否则遍历 __table__.columns）
- _resolve_param_model: 按 param_type_source（device/api）解析目标 PO 类
"""
from __future__ import annotations

from typing import Dict, Any

from algorithm_service.infrastructure.persistence.models import (
    AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    AlgorithmApiParam as AlgorithmApiParamPO,
)


# ========== 辅助函数 ==========

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

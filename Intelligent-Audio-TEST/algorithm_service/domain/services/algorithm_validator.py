# -*- coding: utf-8 -*-
"""算法领域服务 - 校验器。

归属：algorithm_service.domain.services

说明：
- 本模块为纯领域层，不依赖 SQLAlchemy / db.Model。
- AlgorithmValidator 为领域服务，提供与算法相关的纯业务校验逻辑，
  不持有状态，可被 application 层或聚合内部复用。
- 校验失败返回 False，由调用方决定如何抛出领域异常。
"""
from __future__ import annotations

from typing import Any, Dict, List


# 合法的算法参数类型白名单
_VALID_PARAM_TYPES = {
    "text", "audio_stream", "audio_file", "text_file",
    "rttm", "stm", "json", "number", "boolean",
    "textarea", "slider", "switch", "audio_select",
    "device_select",
}


class AlgorithmValidator:
    """算法领域校验服务。"""

    @staticmethod
    def validate_algorithm_type(algorithm_type: str) -> bool:
        """校验算法类型代码是否合法。

        - 非空字符串
        - 仅含字母/数字/下划线
        - 长度不超过 50
        """
        if not algorithm_type or not isinstance(algorithm_type, str):
            return False
        if len(algorithm_type) > 50:
            return False
        if not algorithm_type.replace("_", "").isalnum():
            return False
        # 首字符必须为字母或下划线
        first = algorithm_type[0]
        if not (first.isalpha() or first == "_"):
            return False
        return True

    @staticmethod
    def validate_params(params: List[Dict[str, Any]]) -> bool:
        """校验参数列表是否合法。

        每个参数字典需满足：
        - 含 param_name（非空字符串）
        - 含 param_type（非空字符串且在白名单内）
        - is_required 字段（如存在）必须为布尔
        - sort_order 字段（如存在）必须为整数
        """
        if not isinstance(params, list):
            return False
        for item in params:
            if not isinstance(item, dict):
                return False
            name = item.get("param_name")
            if not name or not isinstance(name, str):
                return False
            ptype = item.get("param_type")
            if not ptype or not isinstance(ptype, str):
                return False
            if ptype not in _VALID_PARAM_TYPES:
                return False
            required = item.get("is_required")
            if required is not None and not isinstance(required, bool):
                return False
            order = item.get("sort_order")
            if order is not None and not isinstance(order, int):
                return False
        return True

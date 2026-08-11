# -*- coding: utf-8 -*-
"""算法配置值对象。

归属：algorithm_service.domain.value_objects

说明：
- 本模块为纯领域层 dataclass，不依赖 SQLAlchemy / db.Model。
- AlgorithmConfig 为值对象，标识某算法的一次具体配置快照
  （algorithm_type + version + params 参数集合）。
- 值对象应视为不可变；如需变更应生成新实例。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class AlgorithmConfig:
    """算法配置值对象。

    - algorithm_type: 算法类型代码
    - version: 算法版本
    - params: 参数键值对集合
    """

    algorithm_type: str
    version: str
    params: Dict[str, Any] = field(default_factory=dict)

# -*- coding: utf-8 -*-
"""算法分组聚合根。

归属：algorithm_service.domain.entities
对应 PO：AlgorithmGroup（algorithm_groups 表）

说明：
- 本模块为纯领域层 dataclass，不依赖 SQLAlchemy / db.Model。
- AlgorithmGroupAggregate 作为算法分组聚合根，承载分组级不变量。
- AlgorithmSnapshot 仅用于分组快照（如导出/缓存场景），不可变。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AlgorithmGroupSnapshot:
    """算法分组快照（不可变视图）。"""

    id: int
    name: str
    description: Optional[str] = None
    algorithm_type: Optional[str] = None


@dataclass
class AlgorithmGroupAggregate:
    """算法分组聚合根。

    - id: 分组ID
    - name: 分组名称（唯一）
    - description: 分组描述
    - algorithm_type: 分组对应的算法类型代码
    - deleted: 逻辑删除标志
    """

    id: int
    name: str
    description: Optional[str] = None
    algorithm_type: Optional[str] = None
    deleted: bool = False

    def to_snapshot(self) -> AlgorithmGroupSnapshot:
        """生成分组快照。"""
        return AlgorithmGroupSnapshot(
            id=self.id,
            name=self.name,
            description=self.description,
            algorithm_type=self.algorithm_type,
        )

    def is_available(self) -> bool:
        """分组是否可用（未删除）。"""
        return not self.deleted

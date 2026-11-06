# -*- coding: utf-8 -*-
"""实验室聚合 - LaboratoryAggregate（INT-655 实验室管理）。

实验室是物理资源归属的聚合根，承载设备 / 播放设备 / 用例的 lab 维度分组。
本模块为纯领域模型，不依赖 SQLAlchemy/db.Model，亦不包含任何 IO 调用。
字段口径对照 doc/总架构/实验室扩展功能设计.md §4.1 与 React laboratory.dto.ts。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class LaboratoryAggregate:
    """实验室聚合根

    属性与 PO 同名字段，供上层直接访问，避免感知 PO。
    deleted 表示逻辑删除标志。
    """
    id: Optional[int] = None
    code: str = ""
    name: str = ""
    building: Optional[str] = None
    floor: Optional[str] = None
    room_number: Optional[str] = None
    description: Optional[str] = None
    status: str = "active"
    deleted: bool = False
    created_at: Any = None
    updated_at: Any = None

    def to_dict(self) -> dict:
        """序列化为 dict（供接口层响应使用）"""
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'building': self.building,
            'floor': self.floor,
            'room_number': self.room_number,
            'description': self.description,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

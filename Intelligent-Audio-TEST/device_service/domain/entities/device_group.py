# -*- coding: utf-8 -*-
"""设备分组实体（INT-80）— 纯领域模型，不依赖 SQLAlchemy。

DeviceGroupEntity 为设备分组聚合根，通过 member_device_ids 维护
组内被测设备集合。区别于 task_service 的用例分组（TestCaseGroupEntity）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class DeviceGroupEntity:
    """设备分组聚合根"""
    id: Optional[str] = None
    name: str = ""
    description: str = ""
    group_type: str = "test"
    created_by_user_id: Optional[int] = None
    updated_by_user_id: Optional[int] = None
    created_at: Any = None
    updated_at: Any = None
    deleted: bool = False
    # 组内设备 ID 集合（聚合边界内的成员关系）
    member_device_ids: List[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'group_type': self.group_type,
            'created_by_user_id': self.created_by_user_id,
            'updated_by_user_id': self.updated_by_user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'device_ids': list(self.member_device_ids),
        }

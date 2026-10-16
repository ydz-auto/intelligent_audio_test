# -*- coding: utf-8 -*-
"""api_gateway 领域层 —— 实验室聚合根（INT-493/INT-537 拆分①）

实验室是网关自有域（设计文档 §7.2「API Gateway 维护 Laboratory 表」授权），
本实体为领域模型（dataclass），非持久化对象；对应 laboratories 表（migration
202608 add_laboratory_tables）字段，持久化映射由 infrastructure 层负责。
"""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from shared.models.common_enums import LabStatus


@dataclass
class Laboratory:
    """实验室聚合根

    status 使用 LabStatus 枚举成员（active/inactive/maintenance），
    落库/透出统一 .value，拒绝魔法字符串。
    """
    id: Optional[int]
    code: str
    name: str
    building: Optional[str] = None
    floor: Optional[str] = None
    room_number: Optional[str] = None
    description: Optional[str] = None
    status: LabStatus = LabStatus.ACTIVE
    deleted: bool = False
    deleted_at: Optional[datetime] = None
    created_by_user_id: Optional[int] = None
    updated_by_user_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> 'Laboratory':
        """从 SQLAlchemy Row（含列名映射）构建实体。

        status 为非枚举值时按 LabStatus 成员校验，未知值抛 ValueError
        （create/update 请求层已用枚举校验，此处为读侧兜底）。
        """
        status = row.status
        if not isinstance(status, LabStatus):
            status = LabStatus(status)
        return cls(
            id=row.id,
            code=row.code,
            name=row.name,
            building=row.building,
            floor=row.floor,
            room_number=row.room_number,
            description=row.description,
            status=status,
            deleted=bool(row.deleted),
            deleted_at=row.deleted_at,
            created_by_user_id=row.created_by_user_id,
            updated_by_user_id=row.updated_by_user_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

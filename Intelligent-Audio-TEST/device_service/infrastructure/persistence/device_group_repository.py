# -*- coding: utf-8 -*-
"""设备分组仓储实现（INT-80）。

PO ↔ Entity 显式转换，仓储方法返回 domain entities，
与 SQLAlchemy 隔离（对齐 DeviceRepository 的 P5+DOMAIN 约定）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

import uuid

from shared.models.database import get_db_session
from device_service.infrastructure.persistence.models import (
    Device,
    DeviceGroup,
    DeviceGroupMember,
)
from device_service.domain.entities import DeviceGroupEntity
from device_service.domain.repositories import DeviceGroupRepositoryInterface


def _group_po_to_entity(po: DeviceGroup, member_device_ids: Optional[List[int]] = None) -> DeviceGroupEntity:
    return DeviceGroupEntity(
        id=po.id,
        name=po.name,
        description=po.description or '',
        group_type=po.group_type or 'test',
        created_by_user_id=po.created_by_user_id,
        updated_by_user_id=po.updated_by_user_id,
        created_at=po.created_at,
        updated_at=po.updated_at,
        deleted=po.deleted,
        member_device_ids=list(member_device_ids or []),
    )


class DeviceGroupRepository(DeviceGroupRepositoryInterface):
    """设备分组仓储"""

    def create_group(self, data: dict, member_device_ids: Optional[List[int]] = None) -> DeviceGroupEntity:
        session = get_db_session()
        group = DeviceGroup(
            id=data.get('id') or str(uuid.uuid4()),
            name=data['name'],
            description=data.get('description') or '',
            group_type=data.get('group_type') or 'test',
            created_by_user_id=data.get('created_by_user_id'),
            updated_by_user_id=data.get('created_by_user_id'),
        )
        session.add(group)
        session.flush()
        for device_id in (member_device_ids or []):
            session.add(DeviceGroupMember(
                group_id=group.id, device_id=int(device_id),
                created_by_user_id=data.get('created_by_user_id'),
            ))
        session.commit()
        return _group_po_to_entity(group, member_device_ids or [])

    def update_group(self, group_id: str, update_fields: dict) -> Optional[DeviceGroupEntity]:
        session = get_db_session()
        group = session.query(DeviceGroup).filter_by(id=group_id, deleted=False).first()
        if not group:
            return None
        for key, value in update_fields.items():
            if hasattr(group, key):
                setattr(group, key, value)
        group.updated_at = datetime.now()
        session.commit()
        return _group_po_to_entity(group, self.get_group_device_ids(group_id))

    def get_group(self, group_id: str) -> Optional[DeviceGroupEntity]:
        session = get_db_session()
        group = session.query(DeviceGroup).filter_by(id=group_id, deleted=False).first()
        if not group:
            return None
        return _group_po_to_entity(group, self.get_group_device_ids(group_id))

    def get_group_by_name(self, name: str) -> Optional[DeviceGroupEntity]:
        session = get_db_session()
        group = session.query(DeviceGroup).filter_by(name=name, deleted=False).first()
        if not group:
            return None
        return _group_po_to_entity(group, self.get_group_device_ids(group.id))

    def delete_group(self, group_id: str, cascade: bool = False) -> bool:
        """软删除分组；cascade=True 时组内设备成员关系一并清除（设备本身保留）"""
        session = get_db_session()
        group = session.query(DeviceGroup).filter_by(id=group_id, deleted=False).first()
        if not group:
            return False
        member_count = session.query(DeviceGroupMember).filter_by(group_id=group_id).count()
        if member_count > 0 and not cascade:
            return False
        group.deleted = True
        group.deleted_at = datetime.now()
        session.query(DeviceGroupMember).filter_by(group_id=group_id).delete()
        session.commit()
        return True

    def list_groups(self, page: int = 1, per_page: int = 100, keyword: str = None,
                    group_type: str = None) -> dict:
        session = get_db_session()
        query = session.query(DeviceGroup).filter_by(deleted=False)
        if keyword:
            query = query.filter(DeviceGroup.name.like(f'%{keyword}%'))
        if group_type:
            query = query.filter(DeviceGroup.group_type == group_type)
        pagination = query.order_by(DeviceGroup.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False)
        counts = self.count_group_devices([g.id for g in pagination.items])
        return {
            'items': [
                {**_group_po_to_entity(g).to_dict(), 'device_count': counts.get(g.id, 0)}
                for g in pagination.items
            ],
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'pages': pagination.pages,
        }

    def add_devices(self, group_id: str, device_ids: List[int]) -> int:
        """批量添加设备到分组（幂等：已存在的跳过），返回实际新增数"""
        session = get_db_session()
        group = session.query(DeviceGroup).filter_by(id=group_id, deleted=False).first()
        if not group:
            return 0
        existing = {
            m.device_id for m in
            session.query(DeviceGroupMember).filter(
                DeviceGroupMember.group_id == group_id,
                DeviceGroupMember.device_id.in_([int(d) for d in device_ids]),
            ).all()
        }
        added = 0
        for device_id in device_ids:
            device_id = int(device_id)
            if device_id in existing:
                continue
            if not session.query(Device).filter_by(id=device_id, deleted=False).first():
                continue
            session.add(DeviceGroupMember(group_id=group_id, device_id=device_id))
            added += 1
        session.commit()
        return added

    def remove_devices(self, group_id: str, device_ids: List[int]) -> int:
        session = get_db_session()
        count = session.query(DeviceGroupMember).filter(
            DeviceGroupMember.group_id == group_id,
            DeviceGroupMember.device_id.in_([int(d) for d in device_ids]),
        ).delete(synchronize_session=False)
        session.commit()
        return count

    def count_group_devices(self, group_ids: List[str]) -> Dict[str, int]:
        if not group_ids:
            return {}
        session = get_db_session()
        rows = session.query(DeviceGroupMember).filter(
            DeviceGroupMember.group_id.in_(group_ids)
        ).all()
        counts: Dict[str, int] = {gid: 0 for gid in group_ids}
        for row in rows:
            counts[row.group_id] = counts.get(row.group_id, 0) + 1
        return counts

    def get_group_device_ids(self, group_id: str) -> List[int]:
        session = get_db_session()
        return [
            m.device_id for m in
            session.query(DeviceGroupMember).filter_by(group_id=group_id).all()
        ]


device_group_repository = DeviceGroupRepository()

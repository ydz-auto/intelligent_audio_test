# -*- coding: utf-8 -*-
"""DeviceRepository - 被测设备仓储实现（从 device_repository.py 拆分，P4-5 大文件拆分）。

P5+DOMAIN: 通过 PO ↔ Entity 显式转换，仓储方法返回 domain entities，
聚合根不再持有 ORM 引用，领域层与 SQLAlchemy 完全隔离。
"""
from typing import List, Optional

from shared.models.database import get_db_session
from device_service.infrastructure.persistence.models import (
    Device,
    DeviceTag,
)
from device_service.domain.entities import DeviceAggregate
from device_service.domain.repositories import DeviceRepositoryInterface
from device_service.infrastructure.persistence._device_converters import (
    _now,
    _device_po_to_entity,
)
from device_service.infrastructure.persistence._device_serializers import (
    _device_to_dict,
)


class DeviceRepository(DeviceRepositoryInterface):
    """被测设备仓储

    P5+DOMAIN: 通过 PO ↔ Entity 显式转换，仓储方法返回 domain entities，
    聚合根不再持有 ORM 引用，领域层与 SQLAlchemy 完全隔离。
    """

    def create_device(self, data: dict) -> DeviceAggregate:
        """创建设备，返回 DeviceAggregate 聚合根。"""
        session = get_db_session()
        new_device = Device(
            name=data['name'],
            model=data['model'],
            description=data.get('description'),
            type=data['type'],
            system=data['system'],
            system_version=data['system_version'],
            app_name=data['app_name'],
            app_version=data['app_version'],
            location=data.get('location'),
            max_audio_duration=data.get('max_audio_duration'),
            needs_prompt_audio=data.get('needs_prompt_audio') or False,
            prompt_config=data.get('prompt_config'),
            connection_type=data.get('connection_type'),
            keywords=data.get('keywords'),
            serial_number=data.get('serial_number'),
            ip=data.get('ip'),
            status=data.get('status') or 'offline',
            supported_algorithms=data.get('supported_algorithms') or [],
        )
        session.add(new_device)
        session.commit()
        return _device_po_to_entity(new_device)

    def update_device(self, device_id: int, update_fields: dict) -> Optional[DeviceAggregate]:
        """更新设备字段，返回更新后的 DeviceAggregate。"""
        session = get_db_session()
        device = session.query(Device).filter_by(id=device_id, deleted=False).first()
        if not device:
            return None
        for key, value in update_fields.items():
            setattr(device, key, value)
        device.updated_at = _now()
        session.commit()
        return _device_po_to_entity(device)

    def get_device(self, device_id: int) -> Optional[DeviceAggregate]:
        """按 ID 查询单个设备，返回 DeviceAggregate。"""
        session = get_db_session()
        po = session.query(Device).filter_by(id=device_id, deleted=False).first()
        if po is None:
            return None
        return _device_po_to_entity(po)

    def delete_device(self, device_id: int) -> bool:
        """软删除设备"""
        session = get_db_session()
        device = session.query(Device).filter_by(id=device_id, deleted=False).first()
        if not device:
            return False
        device.deleted = True
        device.updated_at = _now()
        session.commit()
        return True

    def list_devices(self, page: int = 1, per_page: int = 10, keyword: str = None,
                     status: str = None, device_type: str = None,
                     algorithm_type: str = None) -> dict:
        """分页查询设备列表。

        返回 dict（含 items/total/page 等字段），items 为 Device PO 的序列化 dict，
        用于上层分页/序列化。
        """
        session = get_db_session()
        query = session.query(Device).filter_by(deleted=False)

        if keyword:
            query = query.filter(
                (Device.name.like(f'%{keyword}%')) |
                (Device.model.like(f'%{keyword}%')) |
                (Device.location.like(f'%{keyword}%')) |
                (Device.serial_number.like(f'%{keyword}%')) |
                (Device.app_name.like(f'%{keyword}%')) |
                (Device.ip.like(f'%{keyword}%'))
            )
        if status:
            query = query.filter(Device.status == status)
        if device_type:
            query = query.filter(Device.type == device_type)
        if algorithm_type:
            query = query.filter(Device.supported_algorithms.contains([algorithm_type]))

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        return {
            'items': [_device_to_dict(d) for d in pagination.items],
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'pages': pagination.pages,
        }

    def get_device_statuses(self, device_ids: List[int] = None) -> List[dict]:
        """批量获取设备状态（返回状态摘要 dict 列表）"""
        session = get_db_session()
        if not device_ids:
            devices = session.query(Device).filter_by(deleted=False).all()
        else:
            devices = session.query(Device).filter(
                Device.id.in_(device_ids), Device.deleted == False  # noqa: E712
            ).all()

        return [
            {
                'id': d.id,
                'name': d.name,
                'status': d.status,
                'last_online_at': d.last_online_at.isoformat() if d.last_online_at else None,
            }
            for d in devices
        ]

    def get_devices_by_ids(self, device_ids: list) -> list:
        """按 ID 列表批量查询未删除的设备 PO"""
        if not device_ids:
            return []
        session = get_db_session()
        try:
            return session.query(Device).filter(
                Device.id.in_(device_ids), Device.deleted == False  # noqa: E712
            ).all()
        finally:
            session.close()

    def update_device_status(self, device_id: int, status: str, last_online_at=None) -> bool:
        """更新设备在线状态"""
        session = get_db_session()
        device = session.query(Device).filter_by(id=device_id, deleted=False).first()
        if not device:
            return False
        device.status = status
        if last_online_at is not None:
            device.last_online_at = last_online_at
        device.updated_at = _now()
        session.commit()
        return True

    def check_device_in_tasks(self, device_id: int) -> bool:
        """检查设备是否被任务引用"""
        from device_service.infrastructure.acl.task_acl_repository import task_acl_repository
        return task_acl_repository.check_device_in_tasks(device_id)

    def delete_device_tags(self, device_id: int) -> int:
        """删除设备标签关联"""
        session = get_db_session()
        count = session.query(DeviceTag).filter_by(device_id=device_id).delete()
        session.commit()
        return count

    def get_all_device_serials(self) -> List[str]:
        """获取所有未删除设备的 name 列表（用于扫描时判断是否已注册）"""
        session = get_db_session()
        return [d.name for d in session.query(Device).filter_by(deleted=False).all()]

    # ========== Session 管理 ==========

    def commit(self):
        """提交事务"""
        get_db_session().commit()

    def rollback(self):
        """回滚事务"""
        get_db_session().rollback()

    def flush(self):
        """flush session"""
        get_db_session().flush()

# -*- coding: utf-8 -*-
"""设备配置仓储 — 持久化访问 Device / PlaybackDevice / SPLMapping / CalibrationHistory 等数据。

通过 shared.models.database.get_db_session() 的 scoped_session 访问数据库，
向上层（application/commands/device_command_service、application/queries/device_query_service 等）提供领域可读的接口。

P5+DOMAIN 改造：移除直接返回 PO 对象的 ORM 包装模式，改为 PO ↔ Entity 显式
转换。仓储方法返回 domain entities（DeviceAggregate / PlaybackDeviceAggregate /
SPLMappingEntity 等），而非 PO；上层不再感知 SQLAlchemy ORM。
"""
from typing import List, Optional, Dict, Any

from sqlalchemy import cast, String

from shared.models.database import get_db_session
from device_service.infrastructure.persistence.models import (
    Device,
    DeviceTag,
    PlaybackDevice,
    SPLMapping,
    CalibrationHistory,
)
from device_service.domain.entities import (
    DeviceAggregate,
    DeviceTagEntity,
    PlaybackDeviceAggregate,
    SPLMappingEntity,
    CalibrationHistoryEntity,
)
from device_service.domain.repositories import (
    DeviceRepositoryInterface,
    PlaybackRepositoryInterface,
    SPLRepositoryInterface,
)


def _now():
    from shared.utils.query_utils import now_cst
    return now_cst()


# ========== PO ↔ Entity 转换 ==========

def _device_po_to_entity(po: Device, tags: List[DeviceTagEntity] = None) -> DeviceAggregate:
    """Device PO → DeviceAggregate 聚合根。

    PO 字段映射说明：
        - PO.type → entity.device_type
        - PO.supported_algorithms 等扩展属性放入 entity.config
        - PO.deleted → entity.deleted
    """
    config: Dict[str, Any] = {
        'model': po.model,
        'description': po.description,
        'system': po.system,
        'system_version': po.system_version,
        'app_name': po.app_name,
        'app_version': po.app_version,
        'location': po.location,
        'max_audio_duration': po.max_audio_duration,
        'needs_prompt_audio': po.needs_prompt_audio,
        'prompt_config': po.prompt_config,
        'connection_type': po.connection_type,
        'keywords': po.keywords,
        'serial_number': po.serial_number,
        'ip': getattr(po, 'ip', None),
        'supported_algorithms': po.supported_algorithms or [],
    }
    return DeviceAggregate(
        id=po.id,
        name=po.name or "",
        device_type=po.type or "",
        status=po.status or "offline",
        config=config,
        deleted=po.deleted or False,
        tags=tags or [],
        model=po.model or "",
        description=po.description or "",
        system=po.system or "",
        system_version=po.system_version or "",
        app_name=po.app_name or "",
        app_version=po.app_version or "",
        location=po.location or "",
        max_audio_duration=po.max_audio_duration,
        needs_prompt_audio=po.needs_prompt_audio or False,
        prompt_config=po.prompt_config,
        connection_type=po.connection_type or "",
        keywords=po.keywords,
        serial_number=po.serial_number or "",
        ip=getattr(po, 'ip', None),
        last_online_at=po.last_online_at,
        supported_algorithms=po.supported_algorithms or [],
        created_at=po.created_at,
        updated_at=po.updated_at,
    )


def _apply_device_entity_to_po(aggregate: DeviceAggregate, po: Device) -> None:
    """将 DeviceAggregate 聚合根的可写字段映射回 PO。

    PO 与 entity 字段命名差异在此处显式映射：
        - entity.device_type → PO.type
        - entity.config 中的字段拆分回 PO 各列
    """
    po.name = aggregate.name
    po.type = aggregate.device_type
    po.status = aggregate.status
    po.deleted = aggregate.deleted
    # 从 config 回填扩展字段
    cfg = aggregate.config or {}
    po.model = cfg.get('model', po.model)
    po.description = cfg.get('description', po.description)
    po.system = cfg.get('system', po.system)
    po.system_version = cfg.get('system_version', po.system_version)
    po.app_name = cfg.get('app_name', po.app_name)
    po.app_version = cfg.get('app_version', po.app_version)
    po.location = cfg.get('location', po.location)
    po.max_audio_duration = cfg.get('max_audio_duration', po.max_audio_duration)
    po.needs_prompt_audio = cfg.get('needs_prompt_audio', po.needs_prompt_audio)
    po.prompt_config = cfg.get('prompt_config', po.prompt_config)
    po.connection_type = cfg.get('connection_type', po.connection_type)
    po.keywords = cfg.get('keywords', po.keywords)
    po.serial_number = cfg.get('serial_number', po.serial_number)
    if 'ip' in cfg:
        po.ip = cfg.get('ip')
    po.supported_algorithms = cfg.get('supported_algorithms', po.supported_algorithms)


def _device_tag_po_to_entity(po: DeviceTag, name: str = "") -> DeviceTagEntity:
    """DeviceTag PO → DeviceTagEntity 实体（name 由调用方提供）"""
    return DeviceTagEntity(
        id=po.id,
        device_id=po.device_id,
        name=name,
    )


def _playback_po_to_entity(po: PlaybackDevice) -> PlaybackDeviceAggregate:
    """PlaybackDevice PO → PlaybackDeviceAggregate 聚合根。

    PO 字段映射说明：
        - PO.device_type → entity.device_type
        - PO.is_deleted (0/1) → entity.deleted (bool)
        - 扩展属性放入 entity.config
    """
    config: Dict[str, Any] = {
        'model': po.model,
        'sample_rate': po.sample_rate,
        'channel_index': po.channel_index,
        'device_unique_id': po.device_unique_id,
        'description': po.description,
        'status': po.status,
        'current_spl_mapping_id': po.current_spl_mapping_id,
    }
    return PlaybackDeviceAggregate(
        id=po.id,
        name=po.name or "",
        device_type=po.device_type or "",
        config=config,
        deleted=bool(po.is_deleted),
        model=po.model or "",
        sample_rate=po.sample_rate,
        channel_index=po.channel_index or 0,
        device_unique_id=po.device_unique_id or "",
        description=po.description or "",
        status=po.status or "online",
        current_spl_mapping_id=po.current_spl_mapping_id,
        created_at=po.created_at,
        updated_at=po.updated_at,
    )


def _apply_playback_entity_to_po(aggregate: PlaybackDeviceAggregate, po: PlaybackDevice) -> None:
    """将 PlaybackDeviceAggregate 聚合根的可写字段映射回 PO。"""
    po.name = aggregate.name
    po.device_type = aggregate.device_type
    po.is_deleted = 1 if aggregate.deleted else 0
    cfg = aggregate.config or {}
    if 'model' in cfg:
        po.model = cfg.get('model')
    if 'sample_rate' in cfg:
        po.sample_rate = cfg.get('sample_rate')
    if 'channel_index' in cfg:
        po.channel_index = cfg.get('channel_index')
    if 'device_unique_id' in cfg:
        po.device_unique_id = cfg.get('device_unique_id')
    if 'description' in cfg:
        po.description = cfg.get('description')
    if 'status' in cfg:
        po.status = cfg.get('status')
    if 'current_spl_mapping_id' in cfg:
        po.current_spl_mapping_id = cfg.get('current_spl_mapping_id')


def _spl_mapping_po_to_entity(po: SPLMapping) -> SPLMappingEntity:
    """SPLMapping PO → SPLMappingEntity 实体。

    PO 字段映射说明：
        - PO.target_spl → entity.spl_value
        - PO.test_frequency → entity.frequency
        - PO.updated_at → entity.calibrated_at（时间戳，秒）
    """
    import time
    calibrated_at = 0.0
    if po.updated_at is not None:
        try:
            calibrated_at = po.updated_at.timestamp()
        except (AttributeError, ValueError, OSError):
            calibrated_at = 0.0
    return SPLMappingEntity(
        id=po.id,
        device_id=po.device_id,
        spl_value=po.target_spl or 0.0,
        frequency=po.test_frequency or 1000,
        calibrated_at=calibrated_at,
        name=po.name or "",
        description=po.description or "",
        device_type=po.device_type or "",
        distance=po.distance if po.distance is not None else 1.0,
        target_spl=po.target_spl,
        digital_gain=po.digital_gain,
        test_frequency=po.test_frequency or 1000,
        calibration_status=po.calibration_status or "uncalibrated",
        calibration_data=po.calibration_data,
        deleted=po.deleted or False,
        created_at=po.created_at,
        updated_at=po.updated_at,
    )


def _apply_spl_mapping_entity_to_po(entity: SPLMappingEntity, po: SPLMapping) -> None:
    """将 SPLMappingEntity 可写字段映射回 PO。"""
    po.device_id = entity.device_id
    po.target_spl = entity.spl_value
    po.test_frequency = entity.frequency


def _calibration_history_po_to_entity(po: CalibrationHistory) -> CalibrationHistoryEntity:
    """CalibrationHistory PO → CalibrationHistoryEntity 实体。"""
    import time
    calibrated_at = 0.0
    if po.created_at is not None:
        try:
            calibrated_at = po.created_at.timestamp()
        except (AttributeError, ValueError, OSError):
            calibrated_at = 0.0
    return CalibrationHistoryEntity(
        id=po.id,
        device_id=po.mapping_id,
        calibrated_at=calibrated_at,
        result=str(po.calibration_data) if po.calibration_data is not None else "",
        operator="",
    )


def _device_to_dict(device: Device) -> dict:
    """将 Device ORM 对象序列化为 dict（保留供上层序列化使用）"""
    return {
        'id': device.id,
        'name': device.name,
        'model': device.model,
        'description': device.description,
        'type': device.type,
        'system': device.system,
        'system_version': device.system_version,
        'app_name': device.app_name,
        'app_version': device.app_version,
        'location': device.location,
        'max_audio_duration': device.max_audio_duration,
        'needs_prompt_audio': device.needs_prompt_audio,
        'prompt_config': device.prompt_config,
        'connection_type': device.connection_type,
        'keywords': device.keywords,
        'serial_number': device.serial_number,
        'ip': getattr(device, 'ip', None),
        'status': device.status,
        'last_online_at': device.last_online_at.isoformat() if device.last_online_at else None,
        'created_at': device.created_at.isoformat() if device.created_at else None,
        'updated_at': device.updated_at.isoformat() if device.updated_at else None,
        'supported_algorithms': device.supported_algorithms or [],
    }


def _playback_to_dict(device: PlaybackDevice) -> dict:
    """将 PlaybackDevice ORM 对象序列化为 dict（保留供上层序列化使用）"""
    return {
        'id': device.id,
        'name': device.name,
        'model': device.model,
        'device_type': device.device_type,
        'sample_rate': device.sample_rate,
        'channel_index': device.channel_index,
        'device_unique_id': device.device_unique_id,
        'description': device.description,
        'status': device.status,
        'current_spl_mapping_id': device.current_spl_mapping_id,
        'created_at': device.created_at.isoformat() if device.created_at else None,
        'updated_at': device.updated_at.isoformat() if device.updated_at else None,
    }


def _spl_mapping_to_dict(mapping: SPLMapping, device: PlaybackDevice = None) -> dict:
    """将 SPLMapping ORM 对象序列化为 dict（保留供上层序列化使用）"""
    is_current = False
    if device and device.current_spl_mapping_id == mapping.id:
        is_current = True
    return {
        'id': mapping.id,
        'name': mapping.name,
        'description': mapping.description,
        'device_id': mapping.device_id,
        'device': {'id': device.id, 'name': device.name} if device else None,
        'device_name': device.name if device else '未知设备',
        'device_model': device.model if device else None,
        'device_type': mapping.device_type,
        'distance': mapping.distance,
        'target_spl': mapping.target_spl,
        'digital_gain': mapping.digital_gain,
        'calibration_status': mapping.calibration_status,
        'test_frequency': mapping.test_frequency,
        'calibration_data': mapping.calibration_data,
        'is_current': is_current,
        'created_at': mapping.created_at.isoformat() if mapping.created_at else None,
        'updated_at': mapping.updated_at.isoformat() if mapping.updated_at else None,
    }


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
                Device.id.in_(device_ids), Device.deleted == False
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
                Device.id.in_(device_ids), Device.deleted == False
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


class PlaybackRepository(PlaybackRepositoryInterface):
    """播放设备仓储

    P5+DOMAIN: 通过 PO ↔ Entity 显式转换，仓储方法返回 domain entities
    （PlaybackDeviceAggregate），聚合根不再持有 ORM 引用。
    """

    def create_playback_device(self, data: dict) -> PlaybackDeviceAggregate:
        """创建播放设备，返回 PlaybackDeviceAggregate 聚合根。"""
        session = get_db_session()
        new_device = PlaybackDevice(
            name=data['name'],
            model=data['model'],
            device_type=data['device_type'],
            sample_rate=data['sample_rate'],
            channel_index=data.get('channel_index', 0),
            device_unique_id=data['device_unique_id'],
            description=data.get('description'),
            status=data.get('status', 'online'),
        )
        session.add(new_device)
        session.commit()
        return _playback_po_to_entity(new_device)

    def find_playback_by_unique_and_channel(self, device_unique_id: str, channel_index: int) -> Optional[PlaybackDeviceAggregate]:
        """按唯一标识和通道索引查找未删除的播放设备，返回 PlaybackDeviceAggregate。"""
        session = get_db_session()
        po = session.query(PlaybackDevice).filter_by(
            device_unique_id=device_unique_id,
            channel_index=channel_index,
            is_deleted=0,
        ).first()
        if po is None:
            return None
        return _playback_po_to_entity(po)

    def update_playback_device(self, device_id: int, update_fields: dict) -> Optional[PlaybackDeviceAggregate]:
        """更新播放设备字段，返回更新后的 PlaybackDeviceAggregate。"""
        session = get_db_session()
        device = session.get(PlaybackDevice, device_id)
        if not device:
            return None
        for key, value in update_fields.items():
            setattr(device, key, value)
        device.updated_at = _now()
        session.commit()
        return _playback_po_to_entity(device)

    def get_playback_device(self, device_id: int) -> Optional[PlaybackDeviceAggregate]:
        """按 ID 查询播放设备，返回 PlaybackDeviceAggregate。"""
        session = get_db_session()
        po = session.query(PlaybackDevice).filter_by(id=device_id, is_deleted=0).first()
        if po is None:
            return None
        return _playback_po_to_entity(po)

    def delete_playback_device(self, device_id: int) -> bool:
        """软删除播放设备"""
        session = get_db_session()
        device = session.query(PlaybackDevice).filter_by(id=device_id, is_deleted=0).first()
        if not device:
            return False
        device.is_deleted = 1
        device.updated_at = _now()
        session.commit()
        return True

    def list_playback_devices(self, page: int = 1, per_page: int = 10,
                              keyword: str = None, device_type: str = None) -> dict:
        """分页查询播放设备列表。

        返回 dict（含 items/total/page 等字段），items 为 PlaybackDevice PO 的序列化 dict。
        """
        session = get_db_session()
        query = session.query(PlaybackDevice).filter_by(is_deleted=0)

        if keyword:
            query = query.filter(
                (PlaybackDevice.name.like(f'%{keyword}%')) |
                (PlaybackDevice.model.like(f'%{keyword}%')) |
                (PlaybackDevice.device_unique_id.like(f'%{keyword}%')) |
                (PlaybackDevice.description.like(f'%{keyword}%'))
            )
        if device_type:
            query = query.filter(PlaybackDevice.device_type == device_type)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        return {
            'items': [_playback_to_dict(d) for d in pagination.items],
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'pages': pagination.pages,
        }

    def check_playback_in_testcases(self, device_id: int) -> int:
        """检查播放设备是否被测试用例引用"""
        from device_service.infrastructure.acl.testcase_acl_repository import testcase_acl_repository
        return testcase_acl_repository.check_playback_in_testcases(device_id)

    def update_playback_device_spl_ref(self, device_id: int, spl_mapping_id) -> bool:
        """更新播放设备的 current_spl_mapping_id 引用"""
        session = get_db_session()
        device = session.get(PlaybackDevice, device_id)
        if not device:
            return False
        device.current_spl_mapping_id = spl_mapping_id
        device.updated_at = _now()
        session.commit()
        return True

    def get_all_playback_devices(self) -> List[PlaybackDeviceAggregate]:
        """获取所有未删除播放设备，返回 PlaybackDeviceAggregate 列表。"""
        session = get_db_session()
        pos = session.query(PlaybackDevice).filter_by(is_deleted=0).all()
        return [_playback_po_to_entity(po) for po in pos]

    def find_playback_by_unique_id(self, unique_id: str) -> Optional[PlaybackDeviceAggregate]:
        """按 device_unique_id 查找播放设备，返回 PlaybackDeviceAggregate。"""
        session = get_db_session()
        po = session.query(PlaybackDevice).filter_by(
            device_unique_id=unique_id, is_deleted=0
        ).first()
        if po is None:
            return None
        return _playback_po_to_entity(po)

    def find_playback_limit(self, limit: int = 10) -> List[PlaybackDeviceAggregate]:
        """获取前 N 个播放设备，返回 PlaybackDeviceAggregate 列表。"""
        session = get_db_session()
        pos = session.query(PlaybackDevice).filter_by(is_deleted=0).limit(limit).all()
        return [_playback_po_to_entity(po) for po in pos]

    def batch_update_playback_status(self, status_map: Dict[int, str]) -> int:
        """批量更新播放设备状态"""
        session = get_db_session()
        updated = 0
        now = _now()
        for device_id, new_status in status_map.items():
            device = session.get(PlaybackDevice, device_id)
            if device:
                device.status = new_status
                device.updated_at = now
                updated += 1
        session.commit()
        return updated

    # ========== 批量查询（供 application 层替代直接 PO 查询）==========

    def list_playback_devices_by_unique_ids(self, unique_ids: List[str]) -> List[PlaybackDeviceAggregate]:
        """按 device_unique_id 列表批量查询播放设备。

        供 audio_preview_service 替代 session.query(PlaybackDevice).filter(...).first() 循环。
        """
        session = get_db_session()
        if not unique_ids:
            return []
        pos = session.query(PlaybackDevice).filter(
            PlaybackDevice.device_unique_id.in_(unique_ids),
            PlaybackDevice.is_deleted == 0,
        ).all()
        return [_playback_po_to_entity(po) for po in pos]

    def list_playback_devices_by_ids(self, device_ids: List) -> List[PlaybackDeviceAggregate]:
        """按 ID 列表批量查询播放设备（id 为 int 或 str 均可）。

        供 audio_preview_service 替代 session.get(PlaybackDevice, device_id) 循环。
        """
        session = get_db_session()
        if not device_ids:
            return []
        # 统一转为字符串用于 device_unique_id 查询；若为 int 则按 id 查
        int_ids = [d for d in device_ids if isinstance(d, int)]
        str_ids = [d for d in device_ids if isinstance(d, str)]
        result: List[PlaybackDeviceAggregate] = []

        if int_ids:
            pos = session.query(PlaybackDevice).filter(
                PlaybackDevice.id.in_(int_ids),
                PlaybackDevice.is_deleted == 0,
            ).all()
            result.extend(_playback_po_to_entity(po) for po in pos)

        if str_ids:
            pos = session.query(PlaybackDevice).filter(
                PlaybackDevice.device_unique_id.in_(str_ids),
                PlaybackDevice.is_deleted == 0,
            ).all()
            result.extend(_playback_po_to_entity(po) for po in pos)

        return result

    def get_all_playback_device_name_to_id_map(self) -> Dict[str, int]:
        """查询所有播放设备的 name → id 映射（用于从标注解析 playback_device_name）。

        供 audio_testcase_creation_service 替代直接 query PlaybackDevice PO。
        """
        session = get_db_session()
        pos = session.query(PlaybackDevice).filter_by(is_deleted=0).all()
        result: Dict[str, int] = {}
        for d in pos:
            result.setdefault(d.name, d.id)
        return result

    def find_default_dry_playback_device(self) -> Optional[PlaybackDeviceAggregate]:
        """查询第一个 device_type='dry' 的播放设备（用于 e2e 默认回填）。

        供 audio_testcase_creation_service 替代直接 query PlaybackDevice PO。
        """
        session = get_db_session()
        po = session.query(PlaybackDevice).filter_by(
            device_type='dry', is_deleted=0
        ).first()
        return _playback_po_to_entity(po) if po else None

    def clear_playback_spl_refs(self, mapping_id: int) -> int:
        """清理播放设备中引用此 mapping 的 current_spl_mapping_id"""
        session = get_db_session()
        count = session.query(PlaybackDevice).filter_by(
            current_spl_mapping_id=mapping_id
        ).update({
            'current_spl_mapping_id': None,
            'updated_at': _now(),
        })
        session.commit()
        return count


class SPLRepository(SPLRepositoryInterface):
    """SPL 映射仓储

    P5+DOMAIN: 通过 PO ↔ Entity 显式转换，仓储方法返回 domain entities
    （SPLMappingEntity / CalibrationHistoryEntity），聚合根不再持有 ORM 引用。
    """

    def create_spl_mapping(self, data: dict) -> SPLMappingEntity:
        """创建 SPL 映射，返回 SPLMappingEntity 实体。"""
        session = get_db_session()
        new_mapping = SPLMapping(
            name=data['name'],
            description=data.get('description'),
            device_id=data.get('device_id'),
            device_type=data.get('device_type'),
            distance=data.get('distance') or 1.0,
            target_spl=data.get('target_spl'),
            digital_gain=data.get('digital_gain'),
            test_frequency=data.get('test_frequency') or 1000,
            calibration_status=data.get('calibration_status') or 'uncalibrated',
            calibration_data=data.get('calibration_data'),
        )
        session.add(new_mapping)
        session.flush()
        return _spl_mapping_po_to_entity(new_mapping)

    def update_spl_mapping(self, mapping_id: int, update_fields: dict) -> Optional[SPLMappingEntity]:
        """更新 SPL 映射字段，返回更新后的 SPLMappingEntity。"""
        session = get_db_session()
        mapping = session.get(SPLMapping, mapping_id)
        if not mapping or mapping.deleted:
            return None
        for key, value in update_fields.items():
            setattr(mapping, key, value)
        mapping.updated_at = _now()
        session.commit()
        return _spl_mapping_po_to_entity(mapping)

    def get_spl_mapping(self, mapping_id: int) -> Optional[SPLMappingEntity]:
        """按 ID 查询 SPL 映射，返回 SPLMappingEntity。"""
        session = get_db_session()
        po = session.get(SPLMapping, mapping_id)
        if po is None:
            return None
        return _spl_mapping_po_to_entity(po)

    def delete_spl_mapping(self, mapping_id: int) -> bool:
        """软删除 SPL 映射"""
        session = get_db_session()
        mapping = session.get(SPLMapping, mapping_id)
        if not mapping or mapping.deleted:
            return False
        now = _now()
        mapping.deleted = True
        mapping.deleted_at = now
        mapping.updated_at = now
        session.commit()
        return True

    def list_spl_mappings(self, page: int = 1, per_page: int = 10, keyword: str = None,
                         calibration_status: str = None, device_id: int = None) -> dict:
        """分页查询 SPL 映射列表。

        返回 dict（含 items/total/page 等字段），items 为 SPLMapping PO 的序列化 dict。
        """
        session = get_db_session()
        query = session.query(SPLMapping).filter(SPLMapping.deleted == False)
        if keyword:
            query = query.filter(
                (SPLMapping.name.ilike(f"%{keyword}%")) |
                (SPLMapping.description.ilike(f"%{keyword}%"))
            )
        if calibration_status and calibration_status != 'undefined' and calibration_status != 'all':
            query = query.filter_by(calibration_status=calibration_status)
        if device_id:
            query = query.filter_by(device_id=device_id)

        pagination = query.order_by(SPLMapping.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return {
            'items': [_spl_mapping_to_dict(m) for m in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages,
        }

    def get_spl_mapping_dict(self, mapping_id: int) -> Optional[dict]:
        """按 ID 查询 SPL 映射并返回 dict（含关联设备信息）"""
        session = get_db_session()
        mapping = session.get(SPLMapping, mapping_id)
        if not mapping or mapping.deleted:
            return None
        device = None
        if mapping.device_id:
            device = session.get(PlaybackDevice, mapping.device_id)
        return _spl_mapping_to_dict(mapping, device)

    def get_calibration_history(self, mapping_id: int) -> List[dict]:
        """获取校准历史（返回 dict 列表，兼容上层序列化）"""
        session = get_db_session()
        history = session.query(CalibrationHistory).filter_by(
            mapping_id=mapping_id
        ).order_by(CalibrationHistory.created_at.desc()).all()
        return [
            {
                'id': h.id,
                'calibration_data': h.calibration_data,
                'distance': h.distance,
                'test_frequency': h.test_frequency,
                'created_at': h.created_at.isoformat() if h.created_at else None,
            }
            for h in history
        ]

    def get_spl_stats(self) -> dict:
        """获取 SPL 统计信息"""
        session = get_db_session()
        total = session.query(SPLMapping).filter(SPLMapping.deleted == False).count()
        calibrated = session.query(SPLMapping).filter_by(
            calibration_status='calibrated', deleted=False
        ).count()
        uncalibrated = total - calibrated
        associated_devices = session.query(SPLMapping.device_id).filter(
            SPLMapping.deleted == False
        ).distinct().count()
        return {
            'total': total,
            'calibrated': calibrated,
            'uncalibrated': uncalibrated,
            'associated_devices': associated_devices,
        }

    def get_spl_by_device(self, device_id: int) -> List[dict]:
        """按设备 ID 查询 SPL 映射列表（返回 dict 列表）"""
        session = get_db_session()
        mappings = session.query(SPLMapping).filter_by(
            device_id=device_id, deleted=False
        ).order_by(SPLMapping.created_at.desc()).all()
        return [
            {
                'id': m.id,
                'name': m.name,
                'description': m.description,
                'device_id': m.device_id,
                'device_type': m.device_type,
                'distance': m.distance,
                'target_spl': m.target_spl,
                'calibration_status': m.calibration_status,
                'created_at': m.created_at.isoformat() if m.created_at else None,
                'updated_at': m.updated_at.isoformat() if m.updated_at else None,
            }
            for m in mappings
        ]

    def create_calibration_history(self, mapping_id: int, calibration_data, distance, test_frequency) -> CalibrationHistoryEntity:
        """创建校准历史记录，返回 CalibrationHistoryEntity 实体。"""
        session = get_db_session()
        history = CalibrationHistory(
            mapping_id=mapping_id,
            calibration_data=calibration_data,
            distance=distance,
            test_frequency=test_frequency,
        )
        session.add(history)
        session.commit()
        return _calibration_history_po_to_entity(history)

    def update_playback_device_spl_ref(self, device_id: int, spl_mapping_id) -> bool:
        """更新播放设备的 current_spl_mapping_id 引用"""
        session = get_db_session()
        device = session.get(PlaybackDevice, device_id)
        if not device:
            return False
        device.current_spl_mapping_id = spl_mapping_id
        device.updated_at = _now()
        session.commit()
        return True

    def clear_playback_spl_refs(self, mapping_id: int) -> int:
        """清理播放设备中引用此 mapping 的 current_spl_mapping_id"""
        session = get_db_session()
        count = session.query(PlaybackDevice).filter_by(
            current_spl_mapping_id=mapping_id
        ).update({
            'current_spl_mapping_id': None,
            'updated_at': _now(),
        })
        session.commit()
        return count

    def get_playback_device(self, device_id: int) -> Optional[PlaybackDeviceAggregate]:
        """获取播放设备（用于关联检查），返回 PlaybackDeviceAggregate。"""
        session = get_db_session()
        po = session.get(PlaybackDevice, device_id)
        if po is None:
            return None
        return _playback_po_to_entity(po)

    # ========== 跨域只读查询（CaseAlgorithmParam / AlgorithmReferenceParam）==========
    # 通过 gRPC 调用 algorithm_service.ListCaseParams / ListReferenceParams，
    # 返回 dict 列表；gRPC 不可用时回退直连 PO。

    def list_case_algorithm_params(self, algorithm_type: str):
        """查询指定算法类型的用例参数列表（返回 dict 列表）。

        通过 gRPC 调用 algorithm_service.ListCaseParams，替代直连
        CaseAlgorithmParam PO；gRPC 不可用时回退直连。
        """
        from device_service.infrastructure.acl.algorithm_definition_acl_repository import algorithm_definition_acl_repository
        return algorithm_definition_acl_repository.list_case_params(algorithm_type)

    def list_algorithm_reference_params(self, algorithm_type: str):
        """查询指定算法类型的引用参数列表（返回 dict 列表）。

        通过 gRPC 调用 algorithm_service.ListReferenceParams，替代直连
        AlgorithmReferenceParam PO；gRPC 不可用时返回空列表。
        """
        from device_service.infrastructure.acl.algorithm_definition_acl_repository import algorithm_definition_acl_repository
        return algorithm_definition_acl_repository.list_reference_params(algorithm_type)

    def commit(self):
        """提交事务"""
        get_db_session().commit()

    def rollback(self):
        """回滚事务"""
        get_db_session().rollback()

    def flush(self):
        """flush session"""
        get_db_session().flush()


# ========== 模块级单例（供 application 层依赖注入，避免直接实例化具体类） ==========
device_repository = DeviceRepository()
playback_repository = PlaybackRepository()
spl_repository = SPLRepository()

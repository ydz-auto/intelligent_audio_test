# -*- coding: utf-8 -*-
"""Device PO ↔ Entity 转换器（从 device_repository.py 拆分，P4-5 大文件拆分）。

DeviceAggregate / DeviceTagEntity / PlaybackDeviceAggregate /
SPLMappingEntity / CalibrationHistoryEntity 的双向显式映射（DDD PO ↔ Entity）。

PO 字段映射约定：
- Device.type → DeviceAggregate.device_type
- PlaybackDevice.is_deleted (0/1) → PlaybackDeviceAggregate.deleted (bool)
- SPLMapping.target_spl → SPLMappingEntity.spl_value
- SPLMapping.test_frequency → SPLMappingEntity.frequency
"""
from typing import Any, Dict, List, Optional

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


def _now():
    """获取当前中国标准时间（供各仓储写操作统一使用）。"""
    from shared.utils.query_utils import now_cst
    return now_cst()


# ========== Device PO ↔ Entity ==========

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


# ========== PlaybackDevice PO ↔ Entity ==========

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


# ========== SPLMapping / CalibrationHistory PO ↔ Entity ==========

def _spl_mapping_po_to_entity(po: SPLMapping) -> SPLMappingEntity:
    """SPLMapping PO → SPLMappingEntity 实体。

    PO 字段映射说明：
        - PO.target_spl → entity.spl_value
        - PO.test_frequency → entity.frequency
        - PO.updated_at → entity.calibrated_at（时间戳，秒）
    """
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

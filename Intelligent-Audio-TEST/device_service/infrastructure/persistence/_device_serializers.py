# -*- coding: utf-8 -*-
"""Device PO → dict 序列化器（从 device_repository.py 拆分，P4-5 大文件拆分）。

供上层分页/序列化使用：Device / PlaybackDevice / SPLMapping 的 dict 形态。
"""
from device_service.infrastructure.persistence.models import (
    Device,
    PlaybackDevice,
    SPLMapping,
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

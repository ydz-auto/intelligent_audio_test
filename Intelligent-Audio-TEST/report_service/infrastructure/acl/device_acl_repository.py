# -*- coding: utf-8 -*-
"""device_service ACL 仓储 — gRPC 实现（DeviceConfig / PlaybackConfig）。"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from report_service.config.config import Config
from report_service.domain.dto import DeviceDTO, PlaybackDeviceDTO
from report_service.domain.repositories.acl.device_acl_repository import (
    DeviceConfigAclRepository,
    PlaybackConfigAclRepository,
)
from report_service.infrastructure.acl.lookup_cache import TTLCache
from shared.utils.dto_utils import dict_to_dto

logger = logging.getLogger(__name__)

# 设备配置按 id 缓存（INT-1572 返工）：报告聚合按「每条测试结果」取设备元数据，
# case-averages 实测单次 277 次 GetDevice（10.8s），且是同一批设备的重复取数。
# 只缓存取到的设备（负结果不缓存，新建 / 恢复的设备立即可见）。
_device_cache = TTLCache(
    Config.REPORT_RESOURCE_ACL_CACHE_TTL_SECONDS,
    Config.REPORT_RESOURCE_ACL_CACHE_MAX_ENTRIES,
)


def _attach(dto, payload):
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            logger.debug("附加 result_data 到 DTO 失败", exc_info=True)
    return dto


class DeviceConfigAclRepositoryImpl(DeviceConfigAclRepository):
    """device_service.DeviceConfigService 跨域只读查询 gRPC 实现。"""

    def get_device(self, device_id) -> Optional[DeviceDTO]:
        cached = _device_cache.get(device_id)
        if cached is not None:
            return cached
        from shared.clients.grpc_clients import get_device_config_service_stub
        from shared.proto import e2e_service_pb2 as e2e_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_device_config_service_stub()
            resp = stub.GetDevice(e2e_pb.GetDeviceRequest(device_id=int(device_id)))
            if not resp.success:
                return None
            data = _loads(resp.data, None)
            dto = _attach(dict_to_dto(data, DeviceDTO), data)
            _device_cache.set(device_id, dto)
            return dto
        except Exception as e:
            logger.warning("get_device gRPC failed: %s", e)
            return None

    def get_devices_by_ids(self, device_ids) -> Dict[int, DeviceDTO]:
        if not device_ids:
            return {}
        result: Dict[int, DeviceDTO] = {}
        for did in device_ids:
            d = self.get_device(did)
            if d is not None and d.id is not None:
                try:
                    result[int(d.id)] = d
                except Exception:
                    logger.debug("Device id 转换失败: %r", d.id, exc_info=True)
        return result


class PlaybackConfigAclRepositoryImpl(PlaybackConfigAclRepository):
    """device_service.PlaybackConfigService 跨域只读查询 gRPC 实现。"""

    def get_playback_device(self, device_id) -> Optional[PlaybackDeviceDTO]:
        from shared.clients.grpc_clients import get_playback_config_service_stub
        from shared.proto import e2e_service_pb2 as e2e_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_playback_config_service_stub()
            resp = stub.GetPlaybackDevice(e2e_pb.GetPlaybackDeviceRequest(device_id=int(device_id)))
            if not resp.success:
                return None
            data = _loads(resp.data, None)
            return _attach(dict_to_dto(data, PlaybackDeviceDTO), data)
        except Exception as e:
            logger.warning("get_playback_device gRPC failed: %s", e)
            return None

    def get_playback_devices_by_ids(self, device_ids) -> Dict[int, PlaybackDeviceDTO]:
        if not device_ids:
            return {}
        result_map: Dict[int, PlaybackDeviceDTO] = {}
        for did in device_ids:
            d = self.get_playback_device(did)
            if d is not None and d.id is not None:
                try:
                    result_map[int(d.id)] = d
                except Exception:
                    logger.debug("PlaybackDevice id 转换失败: %r", d.id, exc_info=True)
        return result_map

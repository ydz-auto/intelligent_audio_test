# -*- coding: utf-8 -*-
"""device_service ACL 仓储 — 委托 grpc_proxies 实现。"""
from __future__ import annotations

import logging
from typing import List, Optional

from api_gateway.domain.dto import (
    DeviceDTO, DriverScanDTO, PlaybackDeviceDTO, RegisteredKeywordsDTO, SplMappingDTO,
)
from api_gateway.domain.repositories.acl.device_acl_repository import (
    DeviceAclRepository,
    PlaybackConfigAclRepository,
)
from shared.utils.dto_utils import dict_to_dto

logger = logging.getLogger(__name__)


def _attach(dto, payload):
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            pass
    return dto


def _envelope_data(envelope):
    if isinstance(envelope, dict):
        return envelope.get('data')
    return None


def _items(payload):
    if isinstance(payload, dict):
        return payload.get('items', []) or payload.get('list', [])
    if isinstance(payload, list):
        return payload
    return []


class DeviceAclRepositoryImpl(DeviceAclRepository):
    """device_config_service 实体 + device_driver_factory 只读 ACL 实现。"""

    def get_device(self, device_id) -> Optional[DeviceDTO]:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        data = _envelope_data(device_config_service.get_one(device_id))
        return _attach(dict_to_dto(data, DeviceDTO), data)

    def list_devices(self, **kwargs) -> List[DeviceDTO]:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        data = _envelope_data(device_config_service.get_all(**kwargs))
        return [_attach(dict_to_dto(d, DeviceDTO), d) for d in _items(data) if isinstance(d, dict)]

    def scan_devices(self) -> List[DriverScanDTO]:
        from api_gateway.infrastructure.grpc_proxies import device_driver_factory
        driver = device_driver_factory.get_driver(system='', keywords='')
        data = driver.scan()
        return [_attach(dict_to_dto(d, DriverScanDTO), d) for d in (data or []) if isinstance(d, dict)]

    def get_registered_keywords(self) -> RegisteredKeywordsDTO:
        from api_gateway.infrastructure.grpc_proxies import device_driver_factory
        data = device_driver_factory.get_registered_keywords()
        return _attach(RegisteredKeywordsDTO(keywords=data), data)


class PlaybackConfigAclRepositoryImpl(PlaybackConfigAclRepository):
    """playback_config_service / spl_config_service 实体 ACL 实现。"""

    def get_playback_device(self, device_id) -> Optional[PlaybackDeviceDTO]:
        from api_gateway.infrastructure.grpc_proxies import playback_config_service
        data = _envelope_data(playback_config_service.get_one(device_id))
        return _attach(dict_to_dto(data, PlaybackDeviceDTO), data)

    def list_playback_devices(self, **kwargs) -> List[PlaybackDeviceDTO]:
        from api_gateway.infrastructure.grpc_proxies import playback_config_service
        data = _envelope_data(playback_config_service.get_all(**kwargs))
        return [_attach(dict_to_dto(d, PlaybackDeviceDTO), d) for d in _items(data) if isinstance(d, dict)]

    def get_spl_mapping(self, mapping_id) -> Optional[SplMappingDTO]:
        from api_gateway.infrastructure.grpc_proxies import spl_config_service
        data = _envelope_data(spl_config_service.get_one(mapping_id))
        return _attach(dict_to_dto(data, SplMappingDTO), data)

    def list_spl_mappings(self, **kwargs) -> List[SplMappingDTO]:
        from api_gateway.infrastructure.grpc_proxies import spl_config_service
        data = _envelope_data(spl_config_service.get_all(**kwargs))
        return [_attach(dict_to_dto(d, SplMappingDTO), d) for d in _items(data) if isinstance(d, dict)]

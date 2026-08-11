# -*- coding: utf-8 -*-
"""device_service 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from api_gateway.domain.dto import (
    DeviceDTO, DriverScanDTO, PlaybackDeviceDTO, RegisteredKeywordsDTO, SplMappingDTO,
)


class DeviceAclRepository(ABC):
    """device_config_service 实体查询 + device_driver_factory 只读查询接口。"""

    @abstractmethod
    def get_device(self, device_id) -> Optional[DeviceDTO]:
        ...

    @abstractmethod
    def list_devices(self, **kwargs) -> List[DeviceDTO]:
        ...

    @abstractmethod
    def scan_devices(self) -> List[DriverScanDTO]:
        ...

    @abstractmethod
    def get_registered_keywords(self) -> RegisteredKeywordsDTO:
        ...


class PlaybackConfigAclRepository(ABC):
    """playback_config_service / spl_config_service 实体查询接口。"""

    @abstractmethod
    def get_playback_device(self, device_id) -> Optional[PlaybackDeviceDTO]:
        ...

    @abstractmethod
    def list_playback_devices(self, **kwargs) -> List[PlaybackDeviceDTO]:
        ...

    @abstractmethod
    def get_spl_mapping(self, mapping_id) -> Optional[SplMappingDTO]:
        ...

    @abstractmethod
    def list_spl_mappings(self, **kwargs) -> List[SplMappingDTO]:
        ...

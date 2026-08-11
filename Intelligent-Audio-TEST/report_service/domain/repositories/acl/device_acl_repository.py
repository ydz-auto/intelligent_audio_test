# -*- coding: utf-8 -*-
"""device_service 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional

from report_service.domain.dto import DeviceDTO, PlaybackDeviceDTO


class DeviceConfigAclRepository(ABC):
    """device_service.DeviceConfigService 跨域只读查询接口。"""

    @abstractmethod
    def get_device(self, device_id) -> Optional[DeviceDTO]:
        """查询单个 Device。"""
        ...

    @abstractmethod
    def get_devices_by_ids(self, device_ids) -> Dict[int, DeviceDTO]:
        """批量查询 Device，返回 {id: DeviceDTO}。"""
        ...


class PlaybackConfigAclRepository(ABC):
    """device_service.PlaybackConfigService 跨域只读查询接口。"""

    @abstractmethod
    def get_playback_device(self, device_id) -> Optional[PlaybackDeviceDTO]:
        """查询单个 PlaybackDevice。"""
        ...

    @abstractmethod
    def get_playback_devices_by_ids(self, device_ids) -> Dict[int, PlaybackDeviceDTO]:
        """批量查询 PlaybackDevice，返回 {id: PlaybackDeviceDTO}。"""
        ...

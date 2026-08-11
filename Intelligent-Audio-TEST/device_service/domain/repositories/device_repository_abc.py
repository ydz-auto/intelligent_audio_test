# -*- coding: utf-8 -*-
"""device_service 仓储接口（ABC）— 依赖倒置契约。

domain 层定义接口，infrastructure/persistence/device_repository.py 做实现。
application 层依赖此 ABC，不直接 import 具体仓储类。

遵循 DDD 分层原则：domain 不依赖 SQLAlchemy/db.session 等基础设施。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from device_service.domain.entities import (
    DeviceAggregate,
    PlaybackDeviceAggregate,
    SPLMappingEntity,
    CalibrationHistoryEntity,
)


class DeviceRepositoryInterface(ABC):
    """被测设备仓储接口。"""

    @abstractmethod
    def create_device(self, data: dict) -> DeviceAggregate: ...

    @abstractmethod
    def update_device(self, device_id: int, update_fields: dict) -> Optional[DeviceAggregate]: ...

    @abstractmethod
    def get_device(self, device_id: int) -> Optional[DeviceAggregate]: ...

    @abstractmethod
    def delete_device(self, device_id: int) -> bool: ...

    @abstractmethod
    def list_devices(self, page: int = 1, per_page: int = 10, keyword: str = None, **kwargs) -> Any: ...

    @abstractmethod
    def get_device_statuses(self, device_ids: List[int] = None) -> List[dict]: ...

    @abstractmethod
    def update_device_status(self, device_id: int, status: str, last_online_at=None) -> bool: ...

    @abstractmethod
    def delete_device_tags(self, device_id: int) -> int: ...

    @abstractmethod
    def get_all_device_serials(self) -> List[str]: ...

    # ========== Session 管理 ==========

    @abstractmethod
    def commit(self): ...

    @abstractmethod
    def rollback(self): ...

    @abstractmethod
    def flush(self): ...


class PlaybackRepositoryInterface(ABC):
    """播放设备仓储接口。"""

    @abstractmethod
    def create_playback_device(self, data: dict) -> PlaybackDeviceAggregate: ...

    @abstractmethod
    def restore_playback_device(self, device_id: int, data: dict) -> Optional[PlaybackDeviceAggregate]: ...

    @abstractmethod
    def find_playback_by_unique_and_channel(self, device_unique_id: str, channel_index: int) -> Optional[PlaybackDeviceAggregate]: ...

    @abstractmethod
    def update_playback_device(self, device_id: int, update_fields: dict) -> Optional[PlaybackDeviceAggregate]: ...

    @abstractmethod
    def get_playback_device(self, device_id: int) -> Optional[PlaybackDeviceAggregate]: ...

    @abstractmethod
    def delete_playback_device(self, device_id: int) -> bool: ...

    @abstractmethod
    def list_playback_devices(self, page: int = 1, per_page: int = 10, **kwargs) -> Any: ...

    @abstractmethod
    def update_playback_device_spl_ref(self, device_id: int, spl_mapping_id) -> bool: ...

    @abstractmethod
    def get_all_playback_devices(self) -> List[PlaybackDeviceAggregate]: ...

    @abstractmethod
    def find_playback_by_unique_id(self, unique_id: str) -> Optional[PlaybackDeviceAggregate]: ...

    @abstractmethod
    def find_playback_limit(self, limit: int = 10) -> List[PlaybackDeviceAggregate]: ...

    @abstractmethod
    def batch_update_playback_status(self, status_map: Dict[int, str]) -> int: ...

    @abstractmethod
    def list_playback_devices_by_unique_ids(self, unique_ids: List[str]) -> List[PlaybackDeviceAggregate]: ...

    @abstractmethod
    def list_playback_devices_by_ids(self, device_ids: List) -> List[PlaybackDeviceAggregate]: ...

    @abstractmethod
    def get_all_playback_device_name_to_id_map(self) -> Dict[str, int]: ...

    @abstractmethod
    def find_default_dry_playback_device(self) -> Optional[PlaybackDeviceAggregate]: ...

    @abstractmethod
    def clear_playback_spl_refs(self, mapping_id: int) -> int: ...


class SPLRepositoryInterface(ABC):
    """SPL 映射仓储接口。"""

    @abstractmethod
    def create_spl_mapping(self, data: dict) -> SPLMappingEntity: ...

    @abstractmethod
    def update_spl_mapping(self, mapping_id: int, update_fields: dict) -> Optional[SPLMappingEntity]: ...

    @abstractmethod
    def get_spl_mapping(self, mapping_id: int) -> Optional[SPLMappingEntity]: ...

    @abstractmethod
    def delete_spl_mapping(self, mapping_id: int) -> bool: ...

    @abstractmethod
    def list_spl_mappings(self, page: int = 1, per_page: int = 10, keyword: str = None, **kwargs) -> Any: ...

    @abstractmethod
    def get_spl_mapping_dict(self, mapping_id: int) -> Optional[dict]: ...

    @abstractmethod
    def get_calibration_history(self, mapping_id: int) -> List[dict]: ...

    @abstractmethod
    def get_spl_stats(self) -> dict: ...

    @abstractmethod
    def get_spl_by_device(self, device_id: int) -> List[dict]: ...

    @abstractmethod
    def create_calibration_history(self, mapping_id: int, calibration_data, distance, test_frequency) -> CalibrationHistoryEntity: ...

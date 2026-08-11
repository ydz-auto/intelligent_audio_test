# -*- coding: utf-8 -*-
"""audio_service / audio_config 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from api_gateway.domain.dto import (
    AudioCommandResultDTO, AudioDTO, AudioInfoDTO, DeviceIndexDTO,
    PhysicalDeviceDTO, PlayStatusDTO, SplCommandResultDTO, SplGainDTO,
    SplMeasureResultDTO,
)


class AudioAclRepository(ABC):
    """audio_service 只读数据 + 运行时命令 + audio_config_service 实体查询接口。"""

    # ---- 只读数据 ----

    @abstractmethod
    def get_audio_info(self, task_id, audio_file_path) -> Optional[AudioInfoDTO]:
        ...

    @abstractmethod
    def get_all_physical_devices(self) -> List[PhysicalDeviceDTO]:
        ...

    @abstractmethod
    def get_active_players(self) -> PlayStatusDTO:
        ...

    @abstractmethod
    def measure_spl(self, task_id=None, **kwargs) -> Optional[SplMeasureResultDTO]:
        ...

    # ---- 运行时命令 ----

    @abstractmethod
    def play_audio(self, task_id=None, file_path=None, device_index=0,
                   channel_index=0, gain=0.0, player_type='dry', **kwargs) -> AudioCommandResultDTO:
        ...

    @abstractmethod
    def stop_task_audio(self, task_id) -> None:
        ...

    @abstractmethod
    def get_device_index(self, unique_id) -> Optional[DeviceIndexDTO]:
        ...

    @abstractmethod
    def stop_task_audio_by_pattern(self, task_id_pattern, player_type_pattern=None) -> AudioCommandResultDTO:
        ...

    @abstractmethod
    def start_spl(self, task_id=None, **kwargs) -> SplCommandResultDTO:
        ...

    @abstractmethod
    def stop_spl(self, task_id=None, **kwargs) -> SplCommandResultDTO:
        ...

    @abstractmethod
    def spl_to_gain(self, mapping_id, target_spl, app=None) -> SplGainDTO:
        ...

    # ---- audio_config_service 实体查询 ----

    @abstractmethod
    def get_audio(self, audio_id) -> Optional[AudioDTO]:
        ...

    @abstractmethod
    def list_audios(self, params) -> List[AudioDTO]:
        ...

    @abstractmethod
    def get_audios_by_ids(self, data) -> List[AudioDTO]:
        ...

# -*- coding: utf-8 -*-
"""audio_service / audio_config 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from api_gateway.domain.dto import (
    AudioDTO, AudioInfoDTO, PhysicalDeviceDTO, PlayStatusDTO, SplMeasureResultDTO,
)


class AudioAclRepository(ABC):
    """audio_service 只读数据查询 + audio_config_service 实体查询接口。"""

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

    @abstractmethod
    def get_audio(self, audio_id) -> Optional[AudioDTO]:
        ...

    @abstractmethod
    def list_audios(self, params) -> List[AudioDTO]:
        ...

    @abstractmethod
    def get_audios_by_ids(self, data) -> List[AudioDTO]:
        ...

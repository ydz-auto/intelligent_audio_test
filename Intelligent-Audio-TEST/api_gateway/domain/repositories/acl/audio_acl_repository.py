# -*- coding: utf-8 -*-
"""audio_service / audio_config 跨域 ACL 仓储接口。

运行时命令方法返回特定 DTO（AudioCommandResultDTO 等），
audio_config_service 实体方法返回 CommandResultDTO。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from api_gateway.domain.dto import (
    AudioCommandResultDTO, AudioInfoDTO, CommandResultDTO,
    DeviceIndexDTO, PhysicalDeviceDTO, PlayStatusDTO,
    SplCommandResultDTO, SplGainDTO, SplMeasureResultDTO,
)


class AudioAclRepository(ABC):
    """audio_service 只读数据 + 运行时命令 + audio_config_service 实体 ACL 接口。"""

    # ---- 只读数据 ----

    @abstractmethod
    def get_audio_info(self, task_id, audio_file_path) -> Optional[AudioInfoDTO]: ...

    @abstractmethod
    def get_all_physical_devices(self) -> list[PhysicalDeviceDTO]: ...

    @abstractmethod
    def get_active_players(self) -> PlayStatusDTO: ...

    @abstractmethod
    def measure_spl(self, task_id=None, **kwargs) -> Optional[SplMeasureResultDTO]: ...

    # ---- 运行时命令 ----

    @abstractmethod
    def play_audio(self, task_id=None, file_path=None, device_index=0,
                   channel_index=0, gain=0.0, player_type='dry', **kwargs) -> AudioCommandResultDTO: ...

    @abstractmethod
    def stop_task_audio(self, task_id) -> None: ...

    @abstractmethod
    def get_device_index(self, unique_id) -> Optional[DeviceIndexDTO]: ...

    @abstractmethod
    def stop_task_audio_by_pattern(self, task_id_pattern, player_type_pattern=None) -> AudioCommandResultDTO: ...

    @abstractmethod
    def clear_device_cache(self) -> None: ...

    @abstractmethod
    def start_spl(self, task_id=None, **kwargs) -> SplCommandResultDTO: ...

    @abstractmethod
    def stop_spl(self, task_id=None, **kwargs) -> SplCommandResultDTO: ...

    @abstractmethod
    def spl_to_gain(self, mapping_id, target_spl, app=None) -> SplGainDTO: ...

    # ---- audio_config_service 实体操作 ----

    @abstractmethod
    def get_all(self, params) -> CommandResultDTO: ...

    @abstractmethod
    def get_one(self, audio_id) -> CommandResultDTO: ...

    @abstractmethod
    def get_by_ids(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def get_by_md5(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def get_all_tags(self) -> CommandResultDTO: ...

    @abstractmethod
    def get_all_ids(self, params) -> CommandResultDTO: ...

    @abstractmethod
    def stream_audio(self, audio_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def stream_audio_by_path(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def get_audio_algorithms(self, audio_id) -> CommandResultDTO: ...

    @abstractmethod
    def get_folder_tree(self, params) -> CommandResultDTO: ...

    @abstractmethod
    def get_upload_progress(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update_metadata(self, audio_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def batch_update_annotations(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def batch_action(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete(self, audio_id) -> CommandResultDTO: ...

    @abstractmethod
    def update_audio_algorithms(self, audio_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def batch_update_audio_algorithms(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def convert_audio(self, audio_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def preview_audio(self, audio_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def stop_preview_audio(self, audio_id) -> CommandResultDTO: ...

    @abstractmethod
    def presign_upload(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def presign_part(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def complete_direct_upload(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def init_upload_task(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def register_upload_file(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def upload_chunk(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def merge_chunks(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def url_import(self, data) -> CommandResultDTO: ...

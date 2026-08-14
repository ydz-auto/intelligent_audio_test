# -*- coding: utf-8 -*-
"""audio_service / audio_config ACL 仓储实现 — 委托 grpc_proxies 实现。

运行时命令方法保持特定 DTO 返回，
audio_config_service 实体方法委托 grpc_proxies 并封装为 CommandResultDTO。
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

from api_gateway.domain.dto import (
    AudioCommandResultDTO, AudioInfoDTO, CommandResultDTO,
    DeviceIndexDTO, PhysicalDeviceDTO, PlayStatusDTO,
    SplCommandResultDTO, SplGainDTO, SplMeasureResultDTO,
)
from api_gateway.domain.repositories.acl.audio_acl_repository import (
    AudioAclRepository,
)
from shared.utils.dto_utils import dict_to_dto


def _attach(dto, payload):
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            logger.debug("设置 DTO result_data 失败，dto=%r", dto, exc_info=True)
    return dto


def _wrap(result) -> CommandResultDTO:
    """将 gRPC 返回的信封 dict 封装为 CommandResultDTO。"""
    if isinstance(result, dict):
        return CommandResultDTO(
            success=result.get('success', False),
            message=result.get('message'),
            data=result.get('data'),
            code=result.get('code'),
        )
    return CommandResultDTO(success=False, data=result)


class AudioAclRepositoryImpl(AudioAclRepository):
    """audio_service 只读数据 + 运行时命令 + audio_config_service 实体 ACL 实现。"""

    # ---- 只读数据 ----

    def get_audio_info(self, task_id, audio_file_path) -> Optional[AudioInfoDTO]:
        from api_gateway.infrastructure.grpc_proxies import audio_service
        data = audio_service.get_audio_info(task_id, audio_file_path)
        return _attach(dict_to_dto(data, AudioInfoDTO), data)

    def get_all_physical_devices(self) -> list[PhysicalDeviceDTO]:
        from api_gateway.infrastructure.grpc_proxies import audio_service
        data = audio_service.get_all_physical_devices() or []
        result = []
        for src in data:
            if not isinstance(src, dict):
                continue
            result.append(_attach(dict_to_dto(src, PhysicalDeviceDTO), src))
        return result

    def get_active_players(self) -> PlayStatusDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_service
        data = audio_service.active_players
        dto = PlayStatusDTO(active_players=data)
        return _attach(dto, {'players': data} if isinstance(data, dict) else data)

    def measure_spl(self, task_id=None, **kwargs) -> Optional[SplMeasureResultDTO]:
        from api_gateway.infrastructure.grpc_proxies import spl_service
        data = spl_service.measure_spl(task_id=task_id, **kwargs)
        return _attach(dict_to_dto(data, SplMeasureResultDTO), data)

    # ---- 运行时命令 ----

    def play_audio(self, task_id=None, file_path=None, device_index=0,
                   channel_index=0, gain=0.0, player_type='dry',
                   **kwargs) -> AudioCommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_service
        future = audio_service.play_audio(
            task_id=task_id, file_path=file_path, device_index=device_index,
            channel_index=channel_index, gain=gain, player_type=player_type,
            **kwargs,
        )
        success = getattr(future, '_success', None)
        if success is None and isinstance(future, bool):
            success = future
        return AudioCommandResultDTO(
            success=success,
            result_data={'success': success} if success is not None else None,
        )

    def stop_task_audio(self, task_id) -> None:
        from api_gateway.infrastructure.grpc_proxies import audio_service
        audio_service.stop_task_audio(task_id)
        return None

    def get_device_index(self, unique_id) -> Optional[DeviceIndexDTO]:
        from api_gateway.infrastructure.grpc_proxies import audio_service
        data = audio_service.get_device_index(unique_id)
        dto = DeviceIndexDTO(device_index=data)
        return _attach(dto, {'device_index': data} if data is not None else None)

    def stop_task_audio_by_pattern(self, task_id_pattern,
                                   player_type_pattern=None) -> AudioCommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_service
        success = audio_service.stop_task_audio_by_pattern(
            task_id_pattern, player_type_pattern=player_type_pattern,
        )
        return AudioCommandResultDTO(
            success=success if isinstance(success, bool) else None,
            result_data={'success': success},
        )

    def clear_device_cache(self) -> None:
        from api_gateway.infrastructure.grpc_proxies import audio_service
        audio_service._device_cache = None
        return None

    def start_spl(self, task_id=None, **kwargs) -> SplCommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import spl_service
        success = spl_service.start_spl(task_id=task_id, **kwargs)
        return SplCommandResultDTO(
            success=success if isinstance(success, bool) else None,
            result_data={'success': success},
        )

    def stop_spl(self, task_id=None, **kwargs) -> SplCommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import spl_service
        success = spl_service.stop_spl(task_id=task_id, **kwargs)
        return SplCommandResultDTO(
            success=success if isinstance(success, bool) else None,
            result_data={'success': success},
        )

    def spl_to_gain(self, mapping_id, target_spl, app=None) -> SplGainDTO:
        from api_gateway.infrastructure.grpc_proxies import spl_service
        gain = spl_service.spl_to_gain(mapping_id, target_spl, app=app)
        dto = SplGainDTO(gain=gain)
        return _attach(dto, {'gain': gain} if gain is not None else None)

    # ---- audio_config_service 实体操作 ----

    def get_all(self, params) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.get_all(params))

    def get_one(self, audio_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.get_one(audio_id))

    def get_by_ids(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.get_by_ids(data))

    def get_by_md5(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.get_by_md5(data))

    def get_all_tags(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.get_all_tags())

    def get_all_ids(self, params) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.get_all_ids(params))

    def stream_audio(self, audio_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.stream_audio(audio_id, data))

    def stream_audio_by_path(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.stream_audio_by_path(data))

    def get_audio_algorithms(self, audio_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.get_audio_algorithms(audio_id))

    def get_folder_tree(self, params) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.get_folder_tree(params))

    def get_upload_progress(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.get_upload_progress(data))

    def update_metadata(self, audio_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.update_metadata(audio_id, data))

    def batch_update_annotations(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.batch_update_annotations(data))

    def batch_action(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.batch_action(data))

    def delete(self, audio_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.delete(audio_id))

    def update_audio_algorithms(self, audio_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.update_audio_algorithms(audio_id, data))

    def batch_update_audio_algorithms(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.batch_update_audio_algorithms(data))

    def convert_audio(self, audio_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.convert_audio(audio_id, data))

    def preview_audio(self, audio_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.preview_audio(audio_id, data))

    def stop_preview_audio(self, audio_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.stop_preview_audio(audio_id))

    def presign_upload(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.presign_upload(data))

    def presign_part(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.presign_part(data))

    def complete_direct_upload(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.complete_direct_upload(data))

    def init_upload_task(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.init_upload_task(data))

    def register_upload_file(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.register_upload_file(data))

    def upload_chunk(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.upload_chunk(data))

    def merge_chunks(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.merge_chunks(data))

    def url_import(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        return _wrap(audio_config_service.url_import(data))

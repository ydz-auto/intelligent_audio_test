# -*- coding: utf-8 -*-
"""audio_service / audio_config ACL 仓储 — 委托 grpc_proxies 实现。

委托现有 grpc_proxies 单例完成 gRPC 调用，对返回的 raw dict / 信封 data
负载应用 dict_to_dto / dict_list_to_dto 转换为 dataclass DTO。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from api_gateway.domain.dto import (
    AudioDTO, AudioInfoDTO, PhysicalDeviceDTO, PlayStatusDTO, SplMeasureResultDTO,
)
from api_gateway.domain.repositories.acl.audio_acl_repository import (
    AudioAclRepository,
)
from shared.utils.dto_utils import dict_to_dto, dict_list_to_dto

logger = logging.getLogger(__name__)


def _attach(dto, payload):
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            pass
    return dto


def _envelope_data(envelope):
    """从 {success, message, data, code} 信封提取 data 负载。"""
    if isinstance(envelope, dict):
        return envelope.get('data')
    return None


class AudioAclRepositoryImpl(AudioAclRepository):
    """audio_service 只读数据 + audio_config_service 实体查询 ACL 实现。"""

    def get_audio_info(self, task_id, audio_file_path) -> Optional[AudioInfoDTO]:
        from api_gateway.infrastructure.grpc_proxies import audio_service
        data = audio_service.get_audio_info(task_id, audio_file_path)
        return _attach(dict_to_dto(data, AudioInfoDTO), data)

    def get_all_physical_devices(self) -> List[PhysicalDeviceDTO]:
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

    def get_audio(self, audio_id) -> Optional[AudioDTO]:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        envelope = audio_config_service.get_one(audio_id)
        data = _envelope_data(envelope)
        return _attach(dict_to_dto(data, AudioDTO), data)

    def list_audios(self, params) -> List[AudioDTO]:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        envelope = audio_config_service.get_all(params)
        data = _envelope_data(envelope)
        items = data.get('items', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        return [_attach(dict_to_dto(d, AudioDTO), d) for d in items if isinstance(d, dict)]

    def get_audios_by_ids(self, data) -> List[AudioDTO]:
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        envelope = audio_config_service.get_by_ids(data)
        payload = _envelope_data(envelope)
        items = []
        if isinstance(payload, dict):
            items = payload.get('items', []) or payload.get('list', [])
        elif isinstance(payload, list):
            items = payload
        return [_attach(dict_to_dto(d, AudioDTO), d) for d in items if isinstance(d, dict)]

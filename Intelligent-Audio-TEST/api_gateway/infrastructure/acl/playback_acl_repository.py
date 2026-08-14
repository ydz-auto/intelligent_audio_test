# -*- coding: utf-8 -*-
"""playback_orchestrator ACL 仓储 — 委托 grpc_proxies 实现。

委托现有 playback_orchestrator 单例完成 gRPC 调用，对返回的 raw dict /
bool 负载转换为 PlaybackPreviewResultDTO / PlaybackCommandResultDTO。
"""
from __future__ import annotations

import logging
from typing import Optional

from api_gateway.domain.dto import (
    PlaybackCommandResultDTO,
    PlaybackPreviewResultDTO,
)
from api_gateway.domain.repositories.acl.playback_acl_repository import (
    PlaybackAclRepository,
)
from shared.utils.dto_utils import dict_to_dto

logger = logging.getLogger(__name__)


def _attach(dto, payload):
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            logger.debug("设置 DTO result_data 失败，dto=%r", dto, exc_info=True)
    return dto


class PlaybackAclRepositoryImpl(PlaybackAclRepository):
    """playback_orchestrator 跨域 ACL 实现。"""

    def preview(self, audio_configs=None, case_config=None, task_id=None,
                offset=0, overlap_rate=0, overlap_time=0,
                **kwargs) -> Optional[PlaybackPreviewResultDTO]:
        from api_gateway.infrastructure.grpc_proxies import playback_orchestrator
        data = playback_orchestrator.preview(
            audio_configs=audio_configs,
            case_config=case_config,
            task_id=task_id,
            offset=offset,
            overlap_rate=overlap_rate,
            overlap_time=overlap_time,
            **kwargs,
        )
        return _attach(dict_to_dto(data, PlaybackPreviewResultDTO), data)

    def play_round(self, round_config=None, task_id=None, case_config=None,
                   test_case_id=None, round_number=None,
                   **kwargs) -> Optional[PlaybackPreviewResultDTO]:
        from api_gateway.infrastructure.grpc_proxies import playback_orchestrator
        data = playback_orchestrator.play_round(
            round_config=round_config,
            task_id=task_id,
            case_config=case_config,
            test_case_id=test_case_id,
            round_number=round_number,
            **kwargs,
        )
        return _attach(dict_to_dto(data, PlaybackPreviewResultDTO), data)

    def play_voiceprint(self, voiceprint_config, task_id=None,
                        **kwargs) -> PlaybackCommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import playback_orchestrator
        success = playback_orchestrator.play_voiceprint(
            voiceprint_config, task_id=task_id, **kwargs,
        )
        return PlaybackCommandResultDTO(
            success=success if isinstance(success, bool) else None,
            result_data={'success': success},
        )

    def stop_playback(self, task_id=None, **kwargs) -> None:
        from api_gateway.infrastructure.grpc_proxies import playback_orchestrator
        playback_orchestrator.stop_playback(task_id=task_id, **kwargs)
        return None

# -*- coding: utf-8 -*-
"""PlaybackService ACL 仓储 — gRPC 实现"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from e2e_test_service.domain.dto import PlaybackResultDTO
from e2e_test_service.domain.repositories.playback_acl_repository import (
    PlaybackAclRepository,
)
from shared.utils.dto_utils import dict_to_dto

logger = logging.getLogger(__name__)

_KNOWN = set(PlaybackResultDTO.__dataclass_fields__.keys())


class PlaybackAclRepositoryImpl(PlaybackAclRepository):
    """PlaybackService ACL 仓储实现"""

    def play_voiceprint(self, voiceprint_config: Dict[str, Any], task_id: str) -> bool:
        """播放声纹"""
        from shared.clients.grpc_clients import get_playback_service_stub
        from shared.proto import audio_service_pb2 as audio_pb
        try:
            stub = get_playback_service_stub()
            playback_config = {
                'action': 'play_voiceprint',
                'voiceprint_config': voiceprint_config,
            }
            resp = stub.StartPlayback(audio_pb.StartPlaybackRequest(
                task_id=str(task_id),
                playback_config=json.dumps(playback_config),
            ))
            return resp.success
        except Exception as e:
            logger.error("play_voiceprint 失败: %s", e)
            return False

    def play_round(self, round_config: Dict, task_id: str, case_config: Dict,
                   test_case_id: str, round_number: int,
                   audio_local_paths: Optional[Dict] = None) -> Optional[PlaybackResultDTO]:
        """播放本轮音频"""
        from shared.clients.grpc_clients import get_playback_service_stub
        from shared.proto import audio_service_pb2 as audio_pb
        try:
            stub = get_playback_service_stub()
            playback_config = {
                'action': 'play_round',
                'round_config': round_config,
                'case_config': case_config,
                'test_case_id': test_case_id,
                'round_number': round_number,
                'audio_local_paths': audio_local_paths or {},
            }
            resp = stub.StartPlayback(audio_pb.StartPlaybackRequest(
                task_id=str(task_id),
                playback_config=json.dumps(playback_config),
            ))
            if not resp.success or not resp.data:
                return None
            wrapper = json.loads(resp.data)
            raw = wrapper.get('result') if isinstance(wrapper, dict) else wrapper
            dto = dict_to_dto(raw, PlaybackResultDTO) if isinstance(raw, dict) else None
            if dto and isinstance(raw, dict):
                dto.result_data = {k: v for k, v in raw.items() if k not in _KNOWN}
            return dto
        except Exception as e:
            logger.error("play_round 失败: %s", e)
            return None

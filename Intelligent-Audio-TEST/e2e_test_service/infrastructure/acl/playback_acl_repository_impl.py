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
        """播放本轮音频

        Args:
            audio_local_paths: 嵌套映射 {audio_id: {target_rate: local_path, "original": local_path}}，
                由 PrepareAudios RPC 预下载+重采样生成，按设备 target_rate 取本地文件。
        """
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

    def start_background_noise(self, case_config: Dict, task_id: str) -> Optional[Dict]:
        """启动全局背景噪声（跨轮次持续播放）

        Returns:
            dict: {'audio_id', 'start_ms', 'end_ms'} 启动时间戳（毫秒）
            None: 启动失败
        """
        from shared.clients.grpc_clients import get_playback_service_stub
        from shared.proto import audio_service_pb2 as audio_pb
        try:
            stub = get_playback_service_stub()
            playback_config = {
                'action': 'start_background_noise',
                'case_config': case_config,
            }
            resp = stub.StartPlayback(audio_pb.StartPlaybackRequest(
                task_id=str(task_id),
                playback_config=json.dumps(playback_config),
            ))
            if not resp.success or not resp.data:
                return None
            wrapper = json.loads(resp.data)
            if not wrapper.get('result'):
                return None
            timestamps = wrapper.get('timestamps')
            return timestamps if isinstance(timestamps, dict) else {}
        except Exception as e:
            logger.error("start_background_noise 失败: %s", e)
            return None

    def stop_background_noise(self, task_id: str) -> Optional[Dict]:
        """停止全局背景噪声

        Returns:
            dict: 含 end_ms 的最终时间戳；未启动或失败返回 None
        """
        from shared.clients.grpc_clients import get_playback_service_stub
        from shared.proto import audio_service_pb2 as audio_pb
        try:
            stub = get_playback_service_stub()
            playback_config = {
                'action': 'stop_background_noise',
            }
            resp = stub.StartPlayback(audio_pb.StartPlaybackRequest(
                task_id=str(task_id),
                playback_config=json.dumps(playback_config),
            ))
            if not resp.success or not resp.data:
                return None
            wrapper = json.loads(resp.data)
            timestamps = wrapper.get('timestamps')
            return timestamps if isinstance(timestamps, dict) else None
        except Exception as e:
            logger.error("stop_background_noise 失败: %s", e)
            return None

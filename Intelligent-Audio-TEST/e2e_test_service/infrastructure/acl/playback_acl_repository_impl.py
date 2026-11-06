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

    # 实验室播放设备列表的单页查询量：播放设备是实验室级少量资源（个位数），
    # 一页取全避免分页循环；超出时调用方只会用到首个匹配项，不影响选择口径。
    LAB_PLAYBACK_DEVICE_PAGE_SIZE = 200

    def list_playback_devices(self, lab_id: int) -> list:
        """按实验室查询播放设备（device_service PlaybackConfigService）"""
        from shared.clients.grpc_clients import get_playback_config_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_playback_config_service_stub()
            resp = stub.ListPlaybackDevices(device_pb.ListPlaybackDevicesRequest(
                page=1,
                per_page=self.LAB_PLAYBACK_DEVICE_PAGE_SIZE,
                lab_id=int(lab_id),
            ))
            if not resp.success or not resp.data:
                logger.warning("list_playback_devices 未返回数据: lab_id=%s, msg=%s",
                               lab_id, resp.message)
                return []
            data = json.loads(resp.data)
            items = data.get('items') if isinstance(data, dict) else data
            return [item for item in (items or []) if isinstance(item, dict)]
        except Exception as e:
            logger.error("list_playback_devices 失败: lab_id=%s, error=%s", lab_id, e)
            return []

    def resolve_speaker_device(self, source_device_id: int, target_lab_id: int) -> Optional[int]:
        """解析：源音箱 → 逻辑音箱组 → 目标实验室在该组的设备"""
        from shared.clients.grpc_clients import get_playback_config_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_playback_config_service_stub()
            resp = stub.ResolvePlaybackSpeakerDevice(
                device_pb.ResolvePlaybackSpeakerDeviceRequest(
                    source_device_id=int(source_device_id),
                    target_lab_id=int(target_lab_id),
                ))
            if not resp.success or not resp.data:
                return None
            data = json.loads(resp.data)
            target = data.get('target_device_id') if isinstance(data, dict) else None
            return int(target) if target not in (None, '') else None
        except Exception as e:
            logger.warning("resolve_speaker_device 失败: source=%s, lab=%s, error=%s",
                           source_device_id, target_lab_id, e)
            return None

    def resolve_speaker_group_device(self, group_id: int, target_lab_id: int) -> Optional[int]:
        """解析：逻辑音箱组 + 执行实验室 → 该实验室在组内对应的设备"""
        from shared.clients.grpc_clients import get_playback_config_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_playback_config_service_stub()
            resp = stub.ResolvePlaybackSpeakerGroupDevice(
                device_pb.ResolvePlaybackSpeakerGroupDeviceRequest(
                    group_id=int(group_id),
                    target_lab_id=int(target_lab_id),
                ))
            if not resp.success or not resp.data:
                return None
            data = json.loads(resp.data)
            target = data.get('target_device_id') if isinstance(data, dict) else None
            return int(target) if target not in (None, '') else None
        except Exception as e:
            logger.warning("resolve_speaker_group_device 失败: group=%s, lab=%s, error=%s",
                           group_id, target_lab_id, e)
            return None

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

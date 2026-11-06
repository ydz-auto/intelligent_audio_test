# -*- coding: utf-8 -*-
"""AudioService ACL 仓储 — gRPC 实现

封装 audio_service gRPC 调用，实现 domain/repositories/AudioAclRepository 接口。
替代原 core/e2e_executor/grpc_helpers.py 中的 AudioService 相关函数 + DB 直连。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from e2e_test_service.domain.dto import AudioDTO, PhysicalDeviceDTO, PlayStatusDTO
from e2e_test_service.domain.repositories.audio_acl_repository import (
    AudioAclRepository,
)
from shared.utils.dto_utils import dict_to_dto, dict_list_to_dto

logger = logging.getLogger(__name__)


class AudioAclRepositoryImpl(AudioAclRepository):
    """AudioService ACL 仓储实现"""

    def get_audio_by_id(self, audio_id: int) -> Optional[AudioDTO]:
        """按 ID 获取音频信息（通过 AudioConfigService.GetAudio）"""
        from shared.clients.grpc_clients import get_audio_config_service_stub
        from shared.proto import audio_service_pb2 as audio_pb
        try:
            stub = get_audio_config_service_stub()
            resp = stub.GetAudio(audio_pb.GetAudioRequest(audio_id=int(audio_id)))
            if resp.success and resp.data:
                data = json.loads(resp.data)
                return dict_to_dto(data, AudioDTO) if isinstance(data, dict) else None
            return None
        except Exception as e:
            logger.error("get_audio_by_id 失败: %s", e)
            return None

    def get_prompt_audio(self, audio_id: int) -> Optional[AudioDTO]:
        """获取提示音频（按 ID 查，过滤 audio_type='prompt'）"""
        audio = self.get_audio_by_id(audio_id)
        if audio and audio.audio_type == 'prompt' and not audio.deleted:
            return audio
        return None

    def play_audio(self, task_id: str, file_path: str, device_index: int = 0,
                   channel_index: int = 0, gain: float = 1.0, loop: bool = False,
                   player_type: str = 'dry', offset: int = 0, **kwargs) -> bool:
        """通过 gRPC AudioService.PlayAudio 播放音频"""
        from shared.clients.grpc_clients import get_audio_service_stub
        from shared.proto import audio_service_pb2 as audio_pb
        try:
            stub = get_audio_service_stub()
            play_config = {
                'file_path': file_path, 'device_index': device_index,
                'channel_index': channel_index, 'gain': gain, 'loop': loop,
                'player_type': player_type, 'offset': offset, 'kwargs': kwargs,
            }
            resp = stub.PlayAudio(audio_pb.PlayAudioRequest(
                task_id=str(task_id),
                audio_file_paths=json.dumps([file_path]),
                play_config=json.dumps(play_config),
            ))
            return resp.success
        except Exception as e:
            logger.error("play_audio 失败: %s", e)
            return False

    def stop_audio(self, task_id: str) -> bool:
        """通过 gRPC AudioService.StopAudio 停止音频"""
        from shared.clients.grpc_clients import get_audio_service_stub
        from shared.proto import audio_service_pb2 as audio_pb
        try:
            stub = get_audio_service_stub()
            resp = stub.StopAudio(audio_pb.StopAudioRequest(task_id=str(task_id)))
            return resp.success
        except Exception as e:
            logger.error("stop_audio 失败: %s", e)
            return False

    def stop_audio_by_pattern(self, task_id_pattern: str, player_type_pattern: str) -> int:
        """按模式停止音频，返回停止数量"""
        from shared.clients.grpc_clients import get_audio_service_stub
        from shared.proto import audio_service_pb2 as audio_pb
        try:
            stub = get_audio_service_stub()
            resp = stub.StopAudioByPattern(audio_pb.StopAudioByPatternRequest(
                task_id_pattern=task_id_pattern,
                player_type_pattern=player_type_pattern,
            ))
            if resp.success and resp.data:
                data = json.loads(resp.data)
                return data.get('stopped_count', 0) if isinstance(data, dict) else 0
            return 0
        except Exception as e:
            logger.error("stop_audio_by_pattern 失败: %s", e)
            return 0

    def get_physical_devices(self) -> List[PhysicalDeviceDTO]:
        """获取物理播放设备列表"""
        from shared.clients.grpc_clients import get_audio_service_stub
        from shared.proto import audio_service_pb2 as audio_pb
        try:
            stub = get_audio_service_stub()
            resp = stub.GetPhysicalDevices(audio_pb.GetPhysicalDevicesRequest())
            if resp.success and resp.data:
                data = json.loads(resp.data)
                return dict_list_to_dto(data, PhysicalDeviceDTO) if isinstance(data, list) else []
            return []
        except Exception as e:
            logger.error("get_physical_devices 失败: %s", e)
            return []

    def get_device_index(self, unique_id: str) -> Optional[int]:
        """根据唯一标识获取设备索引"""
        from shared.clients.grpc_clients import get_audio_service_stub
        from shared.proto import audio_service_pb2 as audio_pb
        try:
            stub = get_audio_service_stub()
            resp = stub.GetDeviceIndex(audio_pb.GetDeviceIndexRequest(unique_id=unique_id))
            if resp.success and resp.data:
                data = json.loads(resp.data)
                return data.get('device_index')
            return None
        except Exception as e:
            logger.error("get_device_index 失败: %s", e)
            return None

    def get_play_status(self, task_id: str) -> Optional[PlayStatusDTO]:
        """获取播放状态"""
        from shared.clients.grpc_clients import get_audio_service_stub
        from shared.proto import audio_service_pb2 as audio_pb
        try:
            stub = get_audio_service_stub()
            resp = stub.GetPlayStatus(audio_pb.GetPlayStatusRequest(task_id=str(task_id)))
            if resp.success and resp.data:
                data = json.loads(resp.data)
                return dict_to_dto(data, PlayStatusDTO) if isinstance(data, dict) else None
            return None
        except Exception as e:
            logger.error("get_play_status 失败: %s", e)
            return None

    def get_active_player_keys(self) -> List[str]:
        """获取所有活跃播放器 task_id 列表"""
        status = self.get_play_status('')
        if status and status.active_players:
            return list(status.active_players.keys())
        return []

    def measure_spl(self, mapping_id: str, target_spl: float, **kwargs) -> float:
        """SPL 转增益"""
        from shared.clients.grpc_clients import get_audio_service_stub
        from shared.proto import audio_service_pb2 as audio_pb
        try:
            stub = get_audio_service_stub()
            measure_config = {
                'mapping_id': mapping_id, 'target_spl': target_spl, 'kwargs': kwargs,
            }
            resp = stub.MeasureSPL(audio_pb.MeasureSPLRequest(
                task_id='', measure_config=json.dumps(measure_config),
            ))
            if resp.success and resp.data:
                data = json.loads(resp.data)
                return data.get('gain', 1.0) if isinstance(data, dict) else 1.0
            return 1.0
        except Exception as e:
            logger.error("measure_spl 失败: %s", e)
            return 1.0

    def prepare_audios(self, audio_ids: List[int], playback_device_ids: List[Any]) -> Dict[str, Any]:
        """预下载并按设备目标采样率重采样音频（通过 gRPC AudioService.PrepareAudios）

        Returns:
            嵌套映射 {audio_id: {target_rate: local_path, "original": local_path}} 或空 dict
        """
        from shared.clients.grpc_clients import get_audio_service_stub
        from shared.proto import audio_service_pb2 as audio_pb
        from shared.utils.grpc_json import loads as _loads, dumps as _dumps
        if not audio_ids:
            return {}
        try:
            stub = get_audio_service_stub()
            req = audio_pb.PrepareAudiosRequest(
                data=_dumps({
                    'audio_ids': list(audio_ids),
                    'playback_device_ids': list(playback_device_ids or []),
                }),
            )
            resp = stub.PrepareAudios(req)
            if not resp.success:
                logger.warning("prepare_audios failed: %s", resp.message)
                return {}
            return _loads(resp.data, {}) or {}
        except Exception as e:
            logger.error("prepare_audios 失败: %s", e)
            return {}

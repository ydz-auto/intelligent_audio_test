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

    # play_round 是整轮同步阻塞调用（服务端等音频播完才返回），默认 60s 的
    # gRPC deadline 会把时长 >=60s 的音频直接打断为 DEADLINE_EXCEEDED。
    PLAY_ROUND_TIMEOUT_BUFFER_SECONDS = 120
    # 预下载结果没带 duration（旧版 audio_service）时的保守 deadline
    PLAY_ROUND_TIMEOUT_WITHOUT_DURATION = 600

    @classmethod
    def _collect_audio_ids(cls, node, acc=None):
        """递归收集配置节点中出现的 audio_id（主讲人/噪声/干扰人）。"""
        if acc is None:
            acc = set()
        if isinstance(node, dict):
            audio_id = node.get('audio_id')
            if audio_id not in (None, ''):
                try:
                    acc.add(int(audio_id))
                except (TypeError, ValueError):
                    pass
            for value in node.values():
                cls._collect_audio_ids(value, acc)
        elif isinstance(node, list):
            for item in node:
                cls._collect_audio_ids(item, acc)
        return acc

    @classmethod
    def estimate_play_round_timeout(cls, round_config: Dict,
                                    audio_local_paths: Optional[Dict] = None) -> float:
        """按本轮音频总时长估算 StartPlayback 的显式 deadline（秒）。

        预下载阶段带回每个音频的 duration，求和作为本轮播放时长上界，
        再叠加设备锁等待与播放启动余量。缺少时长信息时回退到保守常量。
        """
        durations = {}
        for audio_id, spec in (audio_local_paths or {}).items():
            if not isinstance(spec, dict):
                continue
            try:
                durations[int(audio_id)] = max(float(spec.get('duration') or 0.0), 0.0)
            except (TypeError, ValueError):
                continue
        total = sum(durations.get(audio_id, 0.0)
                    for audio_id in cls._collect_audio_ids(round_config))
        if total <= 0:
            return float(cls.PLAY_ROUND_TIMEOUT_WITHOUT_DURATION)
        from shared.infrastructure.config import BaseConfig
        lock_wait = float(getattr(BaseConfig, 'PLAYBACK_DEVICE_LOCK_WAIT_SECONDS', 900) or 0)
        return total * 1.2 + lock_wait + cls.PLAY_ROUND_TIMEOUT_BUFFER_SECONDS

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
                   audio_local_paths: Optional[Dict] = None,
                   timeout: Optional[float] = None) -> Optional[PlaybackResultDTO]:
        """播放本轮音频

        Args:
            audio_local_paths: 嵌套映射 {audio_id: {target_rate: local_path, "original": local_path}}，
                由 PrepareAudios RPC 预下载+重采样生成，按设备 target_rate 取本地文件。
            timeout: 显式 RPC deadline（秒）。整轮播放是长阻塞调用，调用方应按本轮
                音频时长传入（见 estimate_play_round_timeout），否则走默认 60s。
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
            request = audio_pb.StartPlaybackRequest(
                task_id=str(task_id),
                playback_config=json.dumps(playback_config),
            )
            if timeout:
                resp = stub.StartPlayback(request, timeout=timeout)
            else:
                resp = stub.StartPlayback(request)
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

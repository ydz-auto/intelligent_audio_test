# -*- coding: utf-8 -*-
"""PlaybackService ACL 仓储接口

e2e_test_service 通过此接口访问 audio_service 的播放编排能力。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class PlaybackAclRepository(ABC):
    """播放服务 ACL 仓储接口"""

    @abstractmethod
    def list_playback_devices(self, lab_id: int) -> list:
        """按实验室查询播放设备（播放设备与被测设备必须同实验室）

        Returns:
            [{id, name, model, status, lab_id, device_type, device_unique_id}, ...]
            查询失败返回空列表（调用方按「该实验室无可用播放设备」处理）
        """

    @abstractmethod
    def resolve_speaker_device(self, source_device_id: int, target_lab_id: int) -> Optional[int]:
        """解析：源音箱 → 所属逻辑音箱组 → 目标实验室在该组的播放设备

        Returns:
            目标播放设备 ID；未配置逻辑音箱组/查询失败返回 None（调用方回退名称匹配）
        """

    @abstractmethod
    def resolve_speaker_group_device(self, group_id: int, target_lab_id: int) -> Optional[int]:
        """解析：逻辑音箱组 + 执行实验室 → 该实验室在组内对应的播放设备

        Returns:
            目标播放设备 ID；组不存在/该实验室未配置/查询失败返回 None（调用方判失败）
        """

    @abstractmethod
    def play_voiceprint(self, voiceprint_config: Dict[str, Any], task_id: str) -> bool:
        """播放声纹"""

    @abstractmethod
    def play_round(self, round_config: Dict, task_id: str, case_config: Dict,
                   test_case_id: str, round_number: int,
                   audio_local_paths: Optional[Dict] = None) -> Optional[Any]:
        """播放本轮音频"""

    @abstractmethod
    def start_background_noise(self, case_config: Dict, task_id: str) -> Optional[Dict]:
        """启动全局背景噪声（跨轮次持续播放）

        Returns:
            dict: {'audio_id', 'start_ms', 'end_ms'} 启动时间戳（毫秒）
            None: 启动失败
        """

    @abstractmethod
    def stop_background_noise(self, task_id: str) -> Optional[Dict]:
        """停止全局背景噪声

        Returns:
            dict: 含 end_ms 的最终时间戳；未启动或失败返回 None
        """

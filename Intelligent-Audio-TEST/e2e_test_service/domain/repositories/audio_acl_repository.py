# -*- coding: utf-8 -*-
"""AudioService ACL 仓储接口

e2e_test_service 通过此接口访问 audio_service 的音频数据与播放能力，
不直接 import shared.models 或 db.session。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class AudioAclRepository(ABC):
    """音频服务 ACL 仓储接口"""

    @abstractmethod
    def get_audio_by_id(self, audio_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 获取音频信息（file_path, name, audio_type 等）"""

    @abstractmethod
    def get_prompt_audio(self, audio_id: int) -> Optional[Dict[str, Any]]:
        """获取提示音频（audio_type='prompt' 的音频）"""

    @abstractmethod
    def play_audio(self, task_id: str, file_path: str, device_index: int = 0,
                   channel_index: int = 0, gain: float = 1.0, loop: bool = False,
                   player_type: str = 'dry', offset: int = 0, **kwargs) -> bool:
        """播放音频"""

    @abstractmethod
    def stop_audio(self, task_id: str) -> bool:
        """停止音频"""

    @abstractmethod
    def stop_audio_by_pattern(self, task_id_pattern: str, player_type_pattern: str) -> int:
        """按模式停止音频，返回停止数量"""

    @abstractmethod
    def get_physical_devices(self) -> List[Dict[str, Any]]:
        """获取物理播放设备列表"""

    @abstractmethod
    def get_device_index(self, unique_id: str) -> Optional[int]:
        """根据唯一标识获取设备索引"""

    @abstractmethod
    def get_play_status(self, task_id: str) -> Dict[str, Any]:
        """获取播放状态"""

    @abstractmethod
    def get_active_player_keys(self) -> List[str]:
        """获取所有活跃播放器 task_id 列表"""

    @abstractmethod
    def measure_spl(self, mapping_id: str, target_spl: float, **kwargs) -> float:
        """SPL 转增益"""

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
    def play_voiceprint(self, voiceprint_config: Dict[str, Any], task_id: str) -> bool:
        """播放声纹"""

    @abstractmethod
    def play_round(self, round_config: Dict, task_id: str, case_config: Dict,
                   test_case_id: str, round_number: int,
                   audio_local_paths: Optional[Dict] = None) -> Optional[Any]:
        """播放本轮音频"""

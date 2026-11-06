# -*- coding: utf-8 -*-
"""播放编排跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from api_gateway.domain.dto import PlaybackCommandResultDTO, PlaybackPreviewResultDTO


class PlaybackAclRepository(ABC):
    """playback_orchestrator 跨域 ACL 仓储接口。

    封装 audio_service PlaybackService 的播放编排调用，
    返回 PlaybackPreviewResultDTO / PlaybackCommandResultDTO（不再返回 raw dict / bool）。
    """

    @abstractmethod
    def preview(self, audio_configs=None, case_config=None, task_id=None,
                offset=0, overlap_rate=0, overlap_time=0,
                **kwargs) -> Optional[PlaybackPreviewResultDTO]:
        ...

    @abstractmethod
    def play_round(self, round_config=None, task_id=None, case_config=None,
                   test_case_id=None, round_number=None,
                   **kwargs) -> Optional[PlaybackPreviewResultDTO]:
        ...

    @abstractmethod
    def play_voiceprint(self, voiceprint_config, task_id=None,
                        **kwargs) -> PlaybackCommandResultDTO:
        ...

    @abstractmethod
    def stop_playback(self, task_id=None, **kwargs) -> None:
        ...

# -*- coding: utf-8 -*-
"""audio_service.AudioConfigService 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from api_test_service.domain.dto import AudioDTO


class AudioConfigAclRepository(ABC):
    """audio_service.AudioConfigService 跨域只读查询接口。"""

    @abstractmethod
    def get_audio(self, audio_id) -> Optional[AudioDTO]:
        """按 ID 查询单个 Audio。"""
        ...

    @abstractmethod
    def get_audio_speakers(self, audio_ids: List) -> Dict[str, List[str]]:
        """批量查询音频 diarization 标注 speaker 集合（INT-99 混音 speakers_map 源）。

        返回 {str(audio_id): [speaker, ...]}；无标注音频返回空列表。
        """
        ...

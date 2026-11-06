# -*- coding: utf-8 -*-
"""audio_service.AudioConfigService 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional

from report_service.domain.dto import AudioDTO


class AudioConfigAclRepository(ABC):
    """audio_service.AudioConfigService 跨域只读查询接口。"""

    @abstractmethod
    def get_audio(self, audio_id) -> Optional[AudioDTO]:
        """查询单个 Audio。"""
        ...

    @abstractmethod
    def get_audios_by_ids(self, audio_ids) -> Dict[int, AudioDTO]:
        """批量查询 Audio，返回 {id: AudioDTO}。"""
        ...

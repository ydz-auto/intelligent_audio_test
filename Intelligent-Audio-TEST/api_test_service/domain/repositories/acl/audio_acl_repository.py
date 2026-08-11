# -*- coding: utf-8 -*-
"""audio_service.AudioConfigService 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from api_test_service.domain.dto import AudioDTO


class AudioConfigAclRepository(ABC):
    """audio_service.AudioConfigService 跨域只读查询接口。"""

    @abstractmethod
    def get_audio(self, audio_id) -> Optional[AudioDTO]:
        """按 ID 查询单个 Audio。"""
        ...

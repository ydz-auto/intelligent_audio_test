# -*- coding: utf-8 -*-
"""audio_service 防腐层仓储接口（ABC）

Domain 层通过此接口访问 audio_service 数据，不直接依赖 infrastructure/acl，
更不允许跨服务裸 SQL 直连 audio_service 自有表（INT-2235 架构红线）。
"""
from abc import ABC, abstractmethod
from typing import Dict, Iterable

from evaluation_service.domain.dto import AudioDTO


class AudioAclRepository(ABC):
    """audio_service 防腐层仓储抽象接口"""

    @abstractmethod
    def get_audios_by_ids(self, audio_ids: Iterable) -> Dict[int, AudioDTO]:
        """按 ID 批量查询未删除音频，返回 {audio_id: AudioDTO}。

        deleted 过滤语义由 audio_service 侧保证：已软删或不存在记录不出现在返回 map 中。
        """
        ...

# -*- coding: utf-8 -*-
"""audio_service 防腐层仓储（ACL Repository）

替代 evaluation_service 直接对 audio_service 自有表 ``audios`` 发裸 SQL 查询
（INT-2235：跨服务一律 gRPC + ACL，不绕网关直连）。

本文件属于 infrastructure 层的防腐层（ACL），封装 ``GetAudiosByIds`` gRPC 调用，
把 audio_service 返回的音频 dict 转换为 evaluation_service 可用的 dataclass DTO。
向上层（domain/services）返回 dataclass DTO，不返回 ORM 对象。

deleted 过滤语义：audio_service 侧 ``get_audios_by_ids`` 只返回 ``deleted == False``
的记录，本 ACL 不再重复过滤；已软删/不存在的 audio_id 不出现在返回 map 中。
"""
import logging
from typing import Dict, Iterable, Optional

from evaluation_service.domain.dto import AudioDTO
from evaluation_service.domain.repositories.audio_acl_repository import (
    AudioAclRepository as _AudioAclRepositoryABC,
)
from shared.clients.grpc_clients import get_audios_by_ids
from shared.utils.dto_utils import dict_to_dto

logger = logging.getLogger(__name__)


def _normalize_audio_id(value) -> Optional[int]:
    """把 audio_id 归一到 int；无法归一（None/空串/非数字）返回 None。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class AudioAclRepository(_AudioAclRepositoryABC):
    """audio_service 防腐层仓储"""

    def get_audios_by_ids(self, audio_ids: Iterable) -> Dict[int, AudioDTO]:
        """批量获取音频（一次 gRPC 调用），返回 {audio_id: AudioDTO}。"""
        normalized = []
        for raw_id in audio_ids or []:
            audio_id = _normalize_audio_id(raw_id)
            if audio_id is not None:
                normalized.append(audio_id)
        # 去重后一次批量取，避免同一音频重复请求（原实现为逐条 N+1 查询）
        normalized = sorted(set(normalized))
        if not normalized:
            return {}

        raw_map = get_audios_by_ids(normalized) or {}
        result: Dict[int, AudioDTO] = {}
        for raw_id, item in raw_map.items():
            audio_id = _normalize_audio_id(raw_id)
            if audio_id is None:
                continue
            dto = dict_to_dto(item, AudioDTO)
            if dto is None:
                continue
            if dto.id is None:
                dto.id = audio_id
            result[audio_id] = dto
        return result


# 模块级单例
audio_acl_repository = AudioAclRepository()

# -*- coding: utf-8 -*-
"""audio_service 读模型查询（Query）定义。

CQRS Query：frozen dataclass，仅描述读意图，不含业务逻辑。
handler 接收 Query 后委托仓储返回领域实体/DTO。
"""
from audio_service.application.queries.audio_queries import (
    ListAudiosQuery,
    GetAudioQuery,
    GetAudiosByIdsQuery,
    GetAudioByMD5Query,
    GetAllAudioIdsQuery,
    GetAllAudioTagsQuery,
    StreamAudioQuery,
    StreamAudioByPathQuery,
    GetAudioAlgorithmsQuery,
    GetAudioFolderTreeQuery,
)

__all__ = [
    "ListAudiosQuery",
    "GetAudioQuery",
    "GetAudiosByIdsQuery",
    "GetAudioByMD5Query",
    "GetAllAudioIdsQuery",
    "GetAllAudioTagsQuery",
    "StreamAudioQuery",
    "StreamAudioByPathQuery",
    "GetAudioAlgorithmsQuery",
    "GetAudioFolderTreeQuery",
]

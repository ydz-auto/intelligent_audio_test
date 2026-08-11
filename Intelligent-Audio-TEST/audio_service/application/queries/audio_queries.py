# -*- coding: utf-8 -*-
"""音频读模型查询（Query）— frozen dataclass，描述读意图。

每个 Query 对应一个读操作，handler 接收后委托仓储返回领域实体/DTO。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class ListAudiosQuery:
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GetAudioQuery:
    audio_id: int


@dataclass(frozen=True)
class GetAudiosByIdsQuery:
    ids: List[int] = field(default_factory=list)


@dataclass(frozen=True)
class GetAudioByMD5Query:
    md5_list: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class GetAllAudioIdsQuery:
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GetAllAudioTagsQuery:
    pass


@dataclass(frozen=True)
class StreamAudioQuery:
    audio_id: int
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StreamAudioByPathQuery:
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GetAudioAlgorithmsQuery:
    audio_id: int


@dataclass(frozen=True)
class GetAudioFolderTreeQuery:
    data: Dict[str, Any] = field(default_factory=dict)

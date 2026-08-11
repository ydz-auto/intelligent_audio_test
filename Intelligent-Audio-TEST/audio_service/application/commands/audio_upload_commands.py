# -*- coding: utf-8 -*-
"""上传写模型命令（Command）— frozen dataclass。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class PresignUploadCommand:
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PresignPartCommand:
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompleteDirectUploadCommand:
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InitUploadTaskCommand:
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RegisterUploadFileCommand:
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UploadChunkCommand:
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MergeChunksCommand:
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GetUploadProgressQuery:
    """上传进度查询（归读侧，但命名沿用 Query 后缀避免与读模型冲突）"""
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UrlImportCommand:
    data: Dict[str, Any] = field(default_factory=dict)

# -*- coding: utf-8 -*-
"""algorithm_service ACL DTO 定义。

供 algorithm_service/infrastructure/acl 下的仓储和 gateway 使用，
将 gRPC 返回的 dict 转换为 dataclass DTO。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ReferenceParamDTO:
    """参考参数 DTO"""
    id: Optional[int] = None
    algorithm_type: Optional[str] = None
    code: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    annotation_code: Optional[str] = None
    annotation_format: Optional[str] = None
    field_path: Optional[str] = None
    merge_mode: Optional[str] = None
    help_text: Optional[str] = None


@dataclass
class AudioDTO:
    """音频 DTO"""
    id: Optional[int] = None
    name: Optional[str] = None
    file_path: Optional[str] = None
    duration: Optional[float] = None
    audio_type: Optional[str] = None
    sample_rate: Optional[int] = None
    annotations: Any = None

# -*- coding: utf-8 -*-
"""音频写模型命令（Command）— frozen dataclass，描述写意图。

每个 Command 对应一个写操作，handler 接收后编排领域服务/仓储执行。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class UpdateAudioMetadataCommand:
    audio_id: int
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BatchUpdateAnnotationsCommand:
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BatchActionAudiosCommand:
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeleteAudioCommand:
    audio_id: int


@dataclass(frozen=True)
class UpdateAudioAlgorithmsCommand:
    audio_id: int
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BatchUpdateAudioAlgorithmsCommand:
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConvertAudioCommand:
    audio_id: int
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PreviewAudioCommand:
    audio_id: int
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StopPreviewAudioCommand:
    audio_id: int


@dataclass(frozen=True)
class PersistAnnotationsCommand:
    audio_id: int
    annotations: List[Dict[str, Any]] = field(default_factory=list)
    algorithm_type: str = ""


@dataclass(frozen=True)
class CreateTestCaseFromAudioCommand:
    audio_id: int
    test_types: List[str] = field(default_factory=lambda: ['api'])
    tags: List[str] = field(default_factory=list)
    default_playback_device_id: Any = None
    default_spl: float = 65.0
    noise_spl: float = 60.0
    noise_audio_id: Any = None
    noise_device_ids: Any = None
    group_name: Any = None
    dimensions_data: Any = None
    algorithm_type: str = ""
    algorithm_params_dict: Any = None
    rounds_config: Any = None
    inherit_tags: bool = True
    raw_annotations: Any = None

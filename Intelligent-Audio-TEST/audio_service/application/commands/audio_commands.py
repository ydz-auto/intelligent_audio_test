# -*- coding: utf-8 -*-
"""音频写模型命令（Command）— frozen dataclass，描述写意图。

每个 Command 对应一个写操作，handler 接收后编排领域服务/仓储执行。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from shared.models.common_enums import DeviceType


@dataclass(frozen=True)
class UpdateAudioMetadataCommand:
    audio_id: int
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UpdateAudioVisibilityCommand:
    """仅更新音频可见性（INT-464 跟随用例 gRPC 同步）。

    内部通道专用：task_service 用例建/改后调用，不对外暴露独立端点。
    """
    audio_id: int
    visibility: str


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
class ProcessAudioCommand:
    """音频处理命令（INT-820 §3.3.2 处理：降噪/增益/剪辑）。"""
    audio_id: int
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreateTestCaseFromAudioCommand:
    audio_id: int
    device_type: str = DeviceType.HTTP_API.value
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
    case_background_noise: Any = None

# -*- coding: utf-8 -*-
"""E2E 测试领域实体（v2 瘦身）。

audio/device 实体已迁移到 audio_service / device_service。
本包保留 re-export 以保持向后兼容。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from e2e_test_service.domain.value_objects import DeviceId, TestResult


@dataclass
class DeviceSession:
    """设备会话实体 - 代表一台被测设备在一次 E2E 测试中的上下文"""
    device_id: DeviceId
    device_sn: str
    device_name: str
    driver: Optional[str] = None
    prompt_audio_path: Optional[str] = None
    prompt_audio_name: Optional[str] = None
    needs_prompt_audio: bool = False
    connected: bool = False

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False


@dataclass
class E2ETestSession:
    """E2E 测试会话聚合根"""
    task_id: str
    tc_rel_id: str
    device_sessions: List[DeviceSession] = field(default_factory=list)
    round_progress: Dict[str, Dict] = field(default_factory=dict)
    results: List[TestResult] = field(default_factory=list)
    status: str = "idle"

    def add_device_session(self, session: DeviceSession):
        self.device_sessions.append(session)

    def mark_running(self):
        self.status = "running"

    def mark_stopping(self):
        self.status = "stopping"

    def mark_completed(self):
        self.status = "completed"

    def mark_failed(self):
        self.status = "failed"

    def update_round_progress(self, round_idx: int, total_rounds: int):
        self.round_progress[self.tc_rel_id] = {
            "round_idx": round_idx,
            "total_rounds": total_rounds,
        }

    def add_result(self, result: TestResult):
        self.results.append(result)

    @property
    def is_terminal(self) -> bool:
        return self.status in ("completed", "failed")


# ---- 本地实体定义 ----
from e2e_test_service.domain.entities.device import (
    DeviceAggregate,
    DeviceTagEntity,
    DeviceSnapshot,
)
from e2e_test_service.domain.entities.playback_device import (
    PlaybackDeviceAggregate,
    PlaybackDeviceSnapshot,
)
from e2e_test_service.domain.entities.spl import (
    SPLMappingEntity,
    CalibrationHistoryEntity,
)
from e2e_test_service.domain.entities.audio import (
    AudioAggregate,
    AudioAnnotationEntity,
    AudioTagEntity,
    AudioAlgorithmRelationEntity,
    AudioSnapshot,
)
from e2e_test_service.domain.entities.upload import (
    UploadTaskAggregate,
    UploadFileEntity,
    UploadChunkEntity,
    UploadStatus,
)

__all__ = [
    # E2E 测试会话
    "DeviceSession",
    "E2ETestSession",
    # 被测设备聚合
    "DeviceAggregate",
    "DeviceTagEntity",
    "DeviceSnapshot",
    "PlaybackDeviceAggregate",
    "PlaybackDeviceSnapshot",
    "SPLMappingEntity",
    "CalibrationHistoryEntity",
    # 音频聚合
    "AudioAggregate",
    "AudioAnnotationEntity",
    "AudioTagEntity",
    "AudioAlgorithmRelationEntity",
    "AudioSnapshot",
    "UploadTaskAggregate",
    "UploadFileEntity",
    "UploadChunkEntity",
    "UploadStatus",
]

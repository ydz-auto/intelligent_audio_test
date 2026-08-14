from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import Field

from api_gateway.schemas.base import APIModel


class HomeStatsRefreshRequest(APIModel):
    pass


class AudioDurationStats(APIModel):
    total: float = Field(default=0)
    dry: float = Field(default=0)
    noise: float = Field(default=0)
    prompt: float = Field(default=0)


class AudioFilesStats(APIModel):
    total: int = Field(default=0)
    dry: int = Field(default=0)
    noise: int = Field(default=0)
    prompt: int = Field(default=0)
    duration: AudioDurationStats = Field(default_factory=AudioDurationStats)


class TasksStats(APIModel):
    total: int = Field(default=0)
    completed: int = Field(default=0)
    running: int = Field(default=0)
    failed: int = Field(default=0)


class DevicesStats(APIModel):
    online: int = Field(default=0)
    offline: int = Field(default=0)
    total: int = Field(default=0)


class ApisStats(APIModel):
    online: int = Field(default=0)
    offline: int = Field(default=0)
    total: int = Field(default=0)


class DimensionsStats(APIModel):
    total: int = Field(default=0)
    with_endpoints: int = Field(default=0)
    endpoints: int = Field(default=0)


class TestCasesStats(APIModel):
    total: int = Field(default=0)
    groups: int = Field(default=0)


class HomeStatsDetails(APIModel):
    test_cases: TestCasesStats = Field(default_factory=TestCasesStats)
    tasks: TasksStats = Field(default_factory=TasksStats)
    devices: DevicesStats = Field(default_factory=DevicesStats)
    audio_files: AudioFilesStats = Field(default_factory=AudioFilesStats)
    playback_devices: int = Field(default=0)
    apis: ApisStats = Field(default_factory=ApisStats)
    reports: int = Field(default=0)
    dimensions: DimensionsStats = Field(default_factory=DimensionsStats)
    updated_at: Optional[str] = Field(default=None)


class DeviceStatus(APIModel):
    online: int = Field(default=0)
    offline: int = Field(default=0)


class RecentTaskItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    type: str = Field(...)
    status: str = Field(...)
    algorithm_type: Optional[str] = Field(None)
    total_cases: int = Field(...)
    completed_cases: int = Field(...)
    created_at: Optional[str] = Field(None)


class TopGroupItem(APIModel):
    id: str = Field(...)
    name: str = Field(...)
    case_count: int = Field(...)


class HomeStatsSummary(APIModel):
    recent_tasks: List[RecentTaskItem] = Field(default_factory=list)
    top_groups: List[TopGroupItem] = Field(default_factory=list)
    device_status: DeviceStatus = Field(default_factory=DeviceStatus)

from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import Field

from api_gateway.schemas.base import APIModel


class HomeStatsRefreshRequest(APIModel):
    pass


class AudioDurationStats(APIModel):
    total: float = Field(default=0, alias='total', validation_alias='total')
    dry: float = Field(default=0, alias='dry', validation_alias='dry')
    noise: float = Field(default=0, alias='noise', validation_alias='noise')
    prompt: float = Field(default=0, alias='prompt', validation_alias='prompt')


class AudioFilesStats(APIModel):
    total: int = Field(default=0, alias='total', validation_alias='total')
    dry: int = Field(default=0, alias='dry', validation_alias='dry')
    noise: int = Field(default=0, alias='noise', validation_alias='noise')
    prompt: int = Field(default=0, alias='prompt', validation_alias='prompt')
    duration: AudioDurationStats = Field(default_factory=AudioDurationStats, alias='duration', validation_alias='duration')


class TasksStats(APIModel):
    total: int = Field(default=0, alias='total', validation_alias='total')
    completed: int = Field(default=0, alias='completed', validation_alias='completed')
    running: int = Field(default=0, alias='running', validation_alias='running')
    failed: int = Field(default=0, alias='failed', validation_alias='failed')


class DevicesStats(APIModel):
    online: int = Field(default=0, alias='online', validation_alias='online')
    offline: int = Field(default=0, alias='offline', validation_alias='offline')
    total: int = Field(default=0, alias='total', validation_alias='total')


class ApisStats(APIModel):
    online: int = Field(default=0, alias='online', validation_alias='online')
    offline: int = Field(default=0, alias='offline', validation_alias='offline')
    total: int = Field(default=0, alias='total', validation_alias='total')


class DimensionsStats(APIModel):
    total: int = Field(default=0, alias='total', validation_alias='total')
    with_endpoints: int = Field(default=0, alias='withEndpoints', validation_alias='withEndpoints')
    endpoints: int = Field(default=0, alias='endpoints', validation_alias='endpoints')


class TestCasesStats(APIModel):
    total: int = Field(default=0, alias='total', validation_alias='total')
    groups: int = Field(default=0, alias='groups', validation_alias='groups')


class HomeStatsDetails(APIModel):
    test_cases: TestCasesStats = Field(default_factory=TestCasesStats, alias='testCases', validation_alias='testCases')
    tasks: TasksStats = Field(default_factory=TasksStats, alias='tasks', validation_alias='tasks')
    devices: DevicesStats = Field(default_factory=DevicesStats, alias='devices', validation_alias='devices')
    audio_files: AudioFilesStats = Field(default_factory=AudioFilesStats, alias='audioFiles', validation_alias='audioFiles')
    playback_devices: int = Field(default=0, alias='playbackDevices', validation_alias='playbackDevices')
    apis: ApisStats = Field(default_factory=ApisStats, alias='apis', validation_alias='apis')
    reports: int = Field(default=0, alias='reports', validation_alias='reports')
    dimensions: DimensionsStats = Field(default_factory=DimensionsStats, alias='dimensions', validation_alias='dimensions')
    updated_at: Optional[str] = Field(default=None, alias='updatedAt', validation_alias='updatedAt')


class DeviceStatus(APIModel):
    online: int = Field(default=0, alias='online', validation_alias='online')
    offline: int = Field(default=0, alias='offline', validation_alias='offline')


class RecentTaskItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    type: str = Field(..., alias='type', validation_alias='type')
    status: str = Field(..., alias='status', validation_alias='status')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    total_cases: int = Field(..., alias='totalCases', validation_alias='totalCases')
    completed_cases: int = Field(..., alias='completedCases', validation_alias='completedCases')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')


class TopGroupItem(APIModel):
    id: str = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    case_count: int = Field(..., alias='caseCount', validation_alias='caseCount')


class HomeStatsSummary(APIModel):
    recent_tasks: List[RecentTaskItem] = Field(default_factory=list, alias='recentTasks', validation_alias='recentTasks')
    top_groups: List[TopGroupItem] = Field(default_factory=list, alias='topGroups', validation_alias='topGroups')
    device_status: DeviceStatus = Field(default_factory=DeviceStatus, alias='deviceStatus', validation_alias='deviceStatus')

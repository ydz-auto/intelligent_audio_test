from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator, model_validator

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class TaskReportItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    status: str = Field(...)
    type: str = Field(...)
    created_at: Optional[str] = Field(None)


class TaskReportsData(APIModel):
    count: int = Field(...)
    reports: List[TaskReportItem] = Field(default_factory=list)


class TaskDeviceBrief(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    status: Optional[str] = Field(None)
    model: Optional[str] = Field(None)


class TaskApiBrief(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    status: Optional[str] = Field(None)


class TaskListItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    status: str = Field(...)
    type: str = Field(...)
    config: Dict[str, Any] = Field(default_factory=dict)
    algorithm_type: Optional[str] = Field(None)
    algorithm_params: Optional[Dict[str, Any]] = Field(None)
    started_at: Optional[str] = Field(None)
    completed_at: Optional[str] = Field(None)
    total_cases: Optional[int] = Field(None)
    case_count: Optional[int] = Field(None)
    device_count: Optional[int] = Field(None)
    completed_cases: Optional[int] = Field(None)
    failed_cases: Optional[int] = Field(None)
    tags: List[str] = Field(default_factory=list)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)
    reports: Optional[TaskReportsData] = Field(None)
    devices: List[TaskDeviceBrief] = Field(default_factory=list)
    apis: List[TaskApiBrief] = Field(default_factory=list)


class TaskListData(PaginatedData[TaskListItem]):
    pass


class TaskCaseBrief(APIModel):
    case_id: str = Field(...)
    name: str = Field(...)
    status: Optional[str] = Field(None)
    execution_status: Optional[str] = Field(None)
    evaluation_status: Optional[str] = Field(None)
    started_at: Optional[str] = Field(None)
    completed_at: Optional[str] = Field(None)
    duration: Optional[float] = Field(None)
    error_message: Optional[str] = Field(None)
    group_name: Optional[str] = Field(None)
    tags: List[str] = Field(default_factory=list)


class TaskDetailData(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    status: str = Field(...)
    type: str = Field(...)
    config: Dict[str, Any] = Field(default_factory=dict)
    algorithm_type: Optional[str] = Field(None)
    algorithm_params: Optional[Dict[str, Any]] = Field(None)
    started_at: Optional[str] = Field(None)
    completed_at: Optional[str] = Field(None)
    expected_total_time: Optional[str] = Field(None)
    expected_complete_time: Optional[str] = Field(None)
    used_time: Optional[str] = Field(None)
    total_cases: Optional[int] = Field(None)
    case_count: Optional[int] = Field(None)
    device_count: Optional[int] = Field(None)
    completed_cases: Optional[int] = Field(None)
    failed_cases: Optional[int] = Field(None)
    tags: List[str] = Field(default_factory=list)
    cases: List[TaskCaseBrief] = Field(default_factory=list)
    devices: List[TaskDeviceBrief] = Field(default_factory=list)
    apis: List[TaskApiBrief] = Field(default_factory=list)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class TaskProgressCurrentCase(APIModel):
    case_id: str = Field(...)
    name: str = Field(...)
    step: Optional[str] = Field(None)
    started_at: Optional[str] = Field(None)


class TaskProgressData(APIModel):
    task_id: str = Field(...)
    status: str = Field(...)
    total_cases: int = Field(...)
    completed_cases: int = Field(...)
    failed_cases: int = Field(...)
    progress: float = Field(...)
    current_case: Optional[TaskProgressCurrentCase] = Field(None)
    updated_at: Optional[str] = Field(None)


class TaskStartData(APIModel):
    task_id: str = Field(...)
    start_time: Any = Field(None)
    status: str = Field(...)
    expected_total_time: Optional[int] = Field(None)
    expected_complete_time: Optional[str] = Field(None)


class TaskUpdateCasesData(APIModel):
    task_id: str = Field(...)
    total_count: int = Field(...)


class TaskStatsData(APIModel):
    total: int = Field(...)
    completed: int = Field(...)
    failed: int = Field(...)
    pending: int = Field(...)
    skipped: int = Field(...)
    pass_rate: float = Field(...)
    tag_stats: Dict[str, Any] = Field(default_factory=dict)
    duration: Any = Field(None)


class TaskCreateParameters(APIModel):
    case_ids: List[str] = Field(default_factory=list)
    device_ids: List[int] = Field(default_factory=list)
    api_ids: List[int] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class TaskCreateRequest(APIModel):
    name: str = Field(...)
    type: str = Field(...)
    description: Optional[str] = Field(None)
    config: Optional[Dict[str, Any]] = Field(None)
    created_by: Optional[str] = Field(None)
    case_ids: Optional[List[str]] = Field(None)
    device_ids: Optional[List[int]] = Field(None)
    api_ids: Optional[List[int]] = Field(None)
    tags: Optional[List[str]] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    algorithm_params: Optional[Dict[str, Any]] = Field(None)


class TaskControlRequest(APIModel):
    action: str = Field(...)
    case_id: Optional[int] = Field(None)


class TaskUpdateCasesRequest(APIModel):
    action: str = Field(...)
    case_ids: List[int] = Field(default_factory=list)


class TaskBatchActionRequest(APIModel):
    action: str = Field(...)
    task_ids: List[int] = Field(default_factory=list)


class TaskMergeRequest(APIModel):
    task_ids: List[int] = Field(default_factory=list)


class TaskListQuery(APIModel):
    page: int = Field(1)
    per_page: int = Field(10)
    status: Optional[str] = Field(None)
    type: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    search: Optional[str] = Field(None)
    start_date: Optional[str] = Field(None)
    end_date: Optional[str] = Field(None)


class TaskBatchExportQuery(APIModel):
    format: str = Field('json')

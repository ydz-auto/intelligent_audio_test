from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator, model_validator

from backend.schemas.base import APIModel
from backend.schemas.common import PaginatedData


class TaskReportItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    status: str = Field(..., alias='status', validation_alias='status')
    type: str = Field(..., alias='type', validation_alias='type')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')


class TaskReportsData(APIModel):
    count: int = Field(..., alias='count', validation_alias='count')
    reports: List[TaskReportItem] = Field(default_factory=list, alias='reports', validation_alias='reports')


class TaskDeviceBrief(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    model: Optional[str] = Field(None, alias='model', validation_alias='model')


class TaskApiBrief(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')


class TaskListItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    status: str = Field(..., alias='status', validation_alias='status')
    type: str = Field(..., alias='type', validation_alias='type')
    config: Dict[str, Any] = Field(default_factory=dict, alias='config', validation_alias='config')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    algorithm_params: Optional[Dict[str, Any]] = Field(None, alias='algorithmParams', validation_alias='algorithmParams')
    started_at: Optional[str] = Field(None, alias='startedAt', validation_alias='startedAt')
    completed_at: Optional[str] = Field(None, alias='completedAt', validation_alias='completedAt')
    total_cases: Optional[int] = Field(None, alias='totalCases', validation_alias='totalCases')
    case_count: Optional[int] = Field(None, alias='caseCount', validation_alias='caseCount')
    device_count: Optional[int] = Field(None, alias='deviceCount', validation_alias='deviceCount')
    completed_cases: Optional[int] = Field(None, alias='completedCases', validation_alias='completedCases')
    failed_cases: Optional[int] = Field(None, alias='failedCases', validation_alias='failedCases')
    tags: List[str] = Field(default_factory=list, alias='tags', validation_alias='tags')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')
    reports: Optional[TaskReportsData] = Field(None, alias='reports', validation_alias='reports')
    devices: List[TaskDeviceBrief] = Field(default_factory=list, alias='devices', validation_alias='devices')
    apis: List[TaskApiBrief] = Field(default_factory=list, alias='apis', validation_alias='apis')


class TaskListData(PaginatedData[TaskListItem]):
    pass


class TaskCaseBrief(APIModel):
    case_id: str = Field(..., alias='caseId', validation_alias='caseId')
    name: str = Field(..., alias='name', validation_alias='name')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    execution_status: Optional[str] = Field(None, alias='executionStatus', validation_alias='executionStatus')
    evaluation_status: Optional[str] = Field(None, alias='evaluationStatus', validation_alias='evaluationStatus')
    started_at: Optional[str] = Field(None, alias='startedAt', validation_alias='startedAt')
    completed_at: Optional[str] = Field(None, alias='completedAt', validation_alias='completedAt')
    duration: Optional[float] = Field(None, alias='duration', validation_alias='duration')
    error_message: Optional[str] = Field(None, alias='errorMessage', validation_alias='errorMessage')
    group_name: Optional[str] = Field(None, alias='groupName', validation_alias='groupName')
    tags: List[str] = Field(default_factory=list, alias='tags', validation_alias='tags')


class TaskDetailData(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    status: str = Field(..., alias='status', validation_alias='status')
    type: str = Field(..., alias='type', validation_alias='type')
    config: Dict[str, Any] = Field(default_factory=dict, alias='config', validation_alias='config')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    algorithm_params: Optional[Dict[str, Any]] = Field(None, alias='algorithmParams', validation_alias='algorithmParams')
    started_at: Optional[str] = Field(None, alias='startedAt', validation_alias='startedAt')
    completed_at: Optional[str] = Field(None, alias='completedAt', validation_alias='completedAt')
    expected_total_time: Optional[str] = Field(None, alias='expectedTotalTime', validation_alias='expectedTotalTime')
    expected_complete_time: Optional[str] = Field(None, alias='expectedCompleteTime', validation_alias='expectedCompleteTime')
    used_time: Optional[str] = Field(None, alias='usedTime', validation_alias='usedTime')
    total_cases: Optional[int] = Field(None, alias='totalCases', validation_alias='totalCases')
    case_count: Optional[int] = Field(None, alias='caseCount', validation_alias='caseCount')
    device_count: Optional[int] = Field(None, alias='deviceCount', validation_alias='deviceCount')
    completed_cases: Optional[int] = Field(None, alias='completedCases', validation_alias='completedCases')
    failed_cases: Optional[int] = Field(None, alias='failedCases', validation_alias='failedCases')
    tags: List[str] = Field(default_factory=list, alias='tags', validation_alias='tags')
    cases: List[TaskCaseBrief] = Field(default_factory=list, alias='cases', validation_alias='cases')
    devices: List[TaskDeviceBrief] = Field(default_factory=list, alias='devices', validation_alias='devices')
    apis: List[TaskApiBrief] = Field(default_factory=list, alias='apis', validation_alias='apis')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')


class TaskProgressCurrentCase(APIModel):
    case_id: str = Field(..., alias='caseId', validation_alias='caseId')
    name: str = Field(..., alias='name', validation_alias='name')
    step: Optional[str] = Field(None, alias='step', validation_alias='step')
    started_at: Optional[str] = Field(None, alias='startedAt', validation_alias='startedAt')


class TaskProgressData(APIModel):
    task_id: str = Field(..., alias='taskId', validation_alias='taskId')
    status: str = Field(..., alias='status', validation_alias='status')
    total_cases: int = Field(..., alias='totalCases', validation_alias='totalCases')
    completed_cases: int = Field(..., alias='completedCases', validation_alias='completedCases')
    failed_cases: int = Field(..., alias='failedCases', validation_alias='failedCases')
    progress: float = Field(..., alias='progress', validation_alias='progress')
    current_case: Optional[TaskProgressCurrentCase] = Field(None, alias='currentCase', validation_alias='currentCase')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')


class TaskStartData(APIModel):
    task_id: str = Field(..., alias='taskId', validation_alias='taskId')
    start_time: Any = Field(None, alias='startTime', validation_alias='startTime')
    status: str = Field(..., alias='status', validation_alias='status')
    expected_total_time: Optional[int] = Field(None, alias='expectedTotalTime', validation_alias='expectedTotalTime')
    expected_complete_time: Optional[str] = Field(None, alias='expectedCompleteTime', validation_alias='expectedCompleteTime')


class TaskUpdateCasesData(APIModel):
    task_id: str = Field(..., alias='taskId', validation_alias='taskId')
    total_count: int = Field(..., alias='totalCount', validation_alias='totalCount')


class TaskStatsData(APIModel):
    total: int = Field(..., alias='total', validation_alias='total')
    completed: int = Field(..., alias='completed', validation_alias='completed')
    failed: int = Field(..., alias='failed', validation_alias='failed')
    pending: int = Field(..., alias='pending', validation_alias='pending')
    skipped: int = Field(..., alias='skipped', validation_alias='skipped')
    pass_rate: float = Field(..., alias='passRate', validation_alias='passRate')
    tag_stats: Dict[str, Any] = Field(default_factory=dict, alias='tagStats', validation_alias='tagStats')
    duration: Any = Field(None, alias='duration', validation_alias='duration')


class TaskCreateParameters(APIModel):
    case_ids: List[str] = Field(default_factory=list, alias='caseIds', validation_alias='caseIds')
    device_ids: List[int] = Field(default_factory=list, alias='deviceIds', validation_alias='deviceIds')
    api_ids: List[int] = Field(default_factory=list, alias='apiIds', validation_alias='apiIds')
    tags: List[str] = Field(default_factory=list, alias='tags', validation_alias='tags')


class TaskCreateRequest(APIModel):
    name: str = Field(..., alias='name', validation_alias='name')
    type: str = Field(..., alias='type', validation_alias='type')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    config: Optional[Dict[str, Any]] = Field(None, alias='config', validation_alias='config')
    created_by: Optional[str] = Field(None, alias='createdBy', validation_alias='createdBy')
    case_ids: Optional[List[str]] = Field(None, alias='caseIds', validation_alias='caseIds')
    device_ids: Optional[List[int]] = Field(None, alias='deviceIds', validation_alias='deviceIds')
    api_ids: Optional[List[int]] = Field(None, alias='apiIds', validation_alias='apiIds')
    tags: Optional[List[str]] = Field(None, alias='tags', validation_alias='tags')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    algorithm_params: Optional[Dict[str, Any]] = Field(None, alias='algorithmParams', validation_alias='algorithmParams')


class TaskControlRequest(APIModel):
    action: str = Field(..., alias='action', validation_alias='action')
    case_id: Optional[int] = Field(None, alias='caseId', validation_alias='caseId')


class TaskUpdateCasesRequest(APIModel):
    action: str = Field(..., alias='action', validation_alias='action')
    case_ids: List[int] = Field(default_factory=list, alias='caseIds', validation_alias='caseIds')


class TaskBatchActionRequest(APIModel):
    action: str = Field(..., alias='action', validation_alias='action')
    task_ids: List[int] = Field(default_factory=list, alias='taskIds', validation_alias='taskIds')


class TaskMergeRequest(APIModel):
    task_ids: List[int] = Field(default_factory=list, alias='taskIds', validation_alias='taskIds')

"""已发布任务 Schema（Published Task Schema）

前后端字段契约：Domain 层见 camelCase；snake_case 仅出现在数据库与 DTO 转换层。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import Field

from backend.schemas.base import APIModel
from backend.schemas.common import PaginatedData


class PublishedTaskCreateRequest(APIModel):
    """发布为已发布任务请求"""
    source_task_id: int = Field(..., alias='sourceTaskId', validation_alias='sourceTaskId')
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    publish_reason: Optional[str] = Field(None, alias='publishReason', validation_alias='publishReason')


class PublishedTaskVersionCreateRequest(APIModel):
    """创建已发布任务新版本请求"""
    source_task_id: Optional[int] = Field(None, alias='sourceTaskId', validation_alias='sourceTaskId')
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    publish_reason: Optional[str] = Field(None, alias='publishReason', validation_alias='publishReason')


class PublishedTaskUpdateRequest(APIModel):
    """重命名已发布任务请求（作用于整个版本链）"""
    name: str = Field(..., alias='name', validation_alias='name')


class PublishedTaskItem(APIModel):
    """已发布任务列表项"""
    id: int = Field(..., alias='id', validation_alias='id')
    source_task_id: Optional[int] = Field(None, alias='sourceTaskId', validation_alias='sourceTaskId')
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    type: str = Field(..., alias='type', validation_alias='type')
    status: str = Field(..., alias='status', validation_alias='status')
    version: int = Field(..., alias='version', validation_alias='version')
    is_current: bool = Field(..., alias='isCurrent', validation_alias='isCurrent')
    version_count: Optional[int] = Field(None, alias='versionCount', validation_alias='versionCount')
    published_by: Optional[str] = Field(None, alias='publishedBy', validation_alias='publishedBy')
    published_at: Optional[str] = Field(None, alias='publishedAt', validation_alias='publishedAt')
    archived_at: Optional[str] = Field(None, alias='archivedAt', validation_alias='archivedAt')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')


class PublishedTaskListData(PaginatedData[PublishedTaskItem]):
    pass


class PublishedTaskDetailData(APIModel):
    """已发布任务详情（元数据 + 快照 + 来源任务摘要）"""
    id: int = Field(..., alias='id', validation_alias='id')
    task_group_id: Optional[int] = Field(None, alias='taskGroupId', validation_alias='taskGroupId')
    source_task_id: Optional[int] = Field(None, alias='sourceTaskId', validation_alias='sourceTaskId')
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    type: str = Field(..., alias='type', validation_alias='type')
    status: str = Field(..., alias='status', validation_alias='status')
    version: int = Field(..., alias='version', validation_alias='version')
    is_current: bool = Field(..., alias='isCurrent', validation_alias='isCurrent')
    snapshot_config: Dict[str, Any] = Field(default_factory=dict, alias='snapshotConfig', validation_alias='snapshotConfig')
    publish_reason: Optional[str] = Field(None, alias='publishReason', validation_alias='publishReason')
    published_by: Optional[str] = Field(None, alias='publishedBy', validation_alias='publishedBy')
    published_at: Optional[str] = Field(None, alias='publishedAt', validation_alias='publishedAt')
    archived_by: Optional[str] = Field(None, alias='archivedBy', validation_alias='archivedBy')
    archived_at: Optional[str] = Field(None, alias='archivedAt', validation_alias='archivedAt')
    source_task_name: Optional[str] = Field(None, alias='sourceTaskName', validation_alias='sourceTaskName')
    source_task_status: Optional[str] = Field(None, alias='sourceTaskStatus', validation_alias='sourceTaskStatus')
    source_task_total_cases: Optional[int] = Field(None, alias='sourceTaskTotalCases', validation_alias='sourceTaskTotalCases')
    source_task_completed_cases: Optional[int] = Field(None, alias='sourceTaskCompletedCases', validation_alias='sourceTaskCompletedCases')
    report_snapshot: Optional[Dict[str, Any]] = Field(None, alias='reportSnapshot', validation_alias='reportSnapshot')
    has_report_snapshot: bool = Field(False, alias='hasReportSnapshot', validation_alias='hasReportSnapshot')
    versions: List[PublishedTaskItem] = Field(default_factory=list, alias='versions', validation_alias='versions')
    execution_history: List[PublishedTaskExecutionItem] = Field(
        default_factory=list, alias='executionHistory', validation_alias='executionHistory'
    )


class PublishedTaskExecutionItem(APIModel):
    """已发布任务版本产生的执行记录（由该版本创建并执行的日常任务）"""
    task_id: int = Field(..., alias='taskId', validation_alias='taskId')
    task_name: str = Field(..., alias='taskName', validation_alias='taskName')
    version: int = Field(..., alias='version', validation_alias='version')
    status: str = Field(..., alias='status', validation_alias='status')
    total_cases: int = Field(0, alias='totalCases', validation_alias='totalCases')
    completed_cases: int = Field(0, alias='completedCases', validation_alias='completedCases')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    completed_at: Optional[str] = Field(None, alias='completedAt', validation_alias='completedAt')


class PublishedTaskExecuteData(APIModel):
    """执行已发布任务返回的新日常任务"""
    task_id: int = Field(..., alias='taskId', validation_alias='taskId')
    task_name: str = Field(..., alias='taskName', validation_alias='taskName')
    published_task_id: int = Field(..., alias='publishedTaskId', validation_alias='publishedTaskId')
    published_task_version: int = Field(..., alias='publishedTaskVersion', validation_alias='publishedTaskVersion')

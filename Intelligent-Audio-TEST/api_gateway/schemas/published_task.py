"""已发布任务 Schema（Published Task Schema）

字段契约对齐 V9.7.10 published_task.py（camelCase 语义），
按 V9.7.31 规范以 snake_case 定义字段（APIModel alias_generator=to_camel
使请求体同时接受 camelCase 与 snake_case；响应序列化为 snake_case）。
snapshot_config / report_snapshot 为不透明 JSON（快照结构保持 camelCase）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import Field

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class PublishedTaskCreateRequest(APIModel):
    """发布为已发布任务请求"""
    source_task_id: int = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    publish_reason: Optional[str] = Field(None)
    benchmark: bool = Field(False, description='是否参与 Benchmark 排行（实测轨数据源标记）')
    benchmark_suite: Optional[str] = Field(None, description='测试集标识（快照 benchmarkSuite，排行分组用）')
    benchmark_category: Optional[str] = Field(
        None, description='被测类别 asr/voice_llm/tts/translation（快照 benchmarkCategory）')


class PublishedTaskVersionCreateRequest(APIModel):
    """创建已发布任务新版本请求"""
    source_task_id: Optional[int] = Field(None)
    name: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    publish_reason: Optional[str] = Field(None)
    benchmark: Optional[bool] = Field(None, description='不传时继承当前版本的 Benchmark 标记')
    benchmark_suite: Optional[str] = Field(None, description='不传时继承当前版本的测试集标识')
    benchmark_category: Optional[str] = Field(None, description='不传时继承当前版本的被测类别')


class PublishedTaskUpdateRequest(APIModel):
    """重命名已发布任务请求（作用于整个版本链）"""
    name: str = Field(...)


class PublishedTaskItem(APIModel):
    """已发布任务列表项"""
    id: int = Field(...)
    source_task_id: Optional[int] = Field(None)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    type: str = Field(...)
    status: str = Field(...)
    benchmark: bool = Field(False, description='是否参与 Benchmark 排行')
    version: int = Field(...)
    is_current: bool = Field(...)
    version_count: Optional[int] = Field(None)
    published_by: Optional[str] = Field(None)
    published_at: Optional[str] = Field(None)
    archived_at: Optional[str] = Field(None)
    created_at: Optional[str] = Field(None)


class PublishedTaskListData(PaginatedData[PublishedTaskItem]):
    pass


class PublishedTaskExecutionItem(APIModel):
    """已发布任务版本产生的执行记录（由该版本创建并执行的日常任务）"""
    task_id: int = Field(...)
    task_name: str = Field(...)
    version: int = Field(...)
    status: str = Field(...)
    total_cases: int = Field(0)
    completed_cases: int = Field(0)
    created_at: Optional[str] = Field(None)
    completed_at: Optional[str] = Field(None)


class PublishedTaskDetailData(APIModel):
    """已发布任务详情（元数据 + 快照 + 来源任务摘要 + 版本历史 + 执行历史）"""
    id: int = Field(...)
    task_group_id: Optional[int] = Field(None)
    source_task_id: Optional[int] = Field(None)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    type: str = Field(...)
    status: str = Field(...)
    benchmark: bool = Field(False, description='是否参与 Benchmark 排行')
    version: int = Field(...)
    is_current: bool = Field(...)
    snapshot_config: Dict[str, Any] = Field(default_factory=dict)
    publish_reason: Optional[str] = Field(None)
    published_by: Optional[str] = Field(None)
    published_at: Optional[str] = Field(None)
    archived_by: Optional[str] = Field(None)
    archived_at: Optional[str] = Field(None)
    source_task_name: Optional[str] = Field(None)
    source_task_status: Optional[str] = Field(None)
    source_task_total_cases: Optional[int] = Field(None)
    source_task_completed_cases: Optional[int] = Field(None)
    report_snapshot: Optional[Dict[str, Any]] = Field(None)
    has_report_snapshot: bool = Field(False)
    versions: List[PublishedTaskItem] = Field(default_factory=list)
    execution_history: List[PublishedTaskExecutionItem] = Field(default_factory=list)


class PublishedTaskExecuteData(APIModel):
    """执行已发布任务返回的新日常任务"""
    task_id: int = Field(...)
    task_name: str = Field(...)
    published_task_id: int = Field(...)
    published_task_version: int = Field(...)

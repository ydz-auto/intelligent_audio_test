from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator, model_validator

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class TaskReportItem(APIModel):
    # 报告聚合（report_service）不含 name/type 字段（只有 report_type），
    # 上游可能缺失，必须容错为 Optional，避免 /tasks 列表 500
    id: int = Field(...)
    name: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    type: Optional[str] = Field(None)
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


class TaskSourceBrief(APIModel):
    """合并任务来源任务摘要（TaskMergeRelation.source_task 简报）。"""
    id: int = Field(...)
    name: str = Field(...)
    status: Optional[str] = Field(None)
    total_cases: Optional[int] = Field(None)
    completed_cases: Optional[int] = Field(None)
    failed_cases: Optional[int] = Field(None)
    created_at: Optional[str] = Field(None)


class TaskListItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    status: str = Field(...)
    # INT-301：任务级执行/评估双状态（评估推进只落评估侧，与执行完全分离）
    execution_status: Optional[str] = Field(None)
    evaluation_status: Optional[str] = Field(None)
    device_types: List[str] = Field(default_factory=list)
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
    # INT-141：收藏标记 / 回收站字段
    is_favorite: Optional[bool] = Field(None)
    deleted: Optional[bool] = Field(None)
    deleted_at: Optional[str] = Field(None)
    deleted_by_user_id: Optional[int] = Field(None)
    reports: Optional[TaskReportsData] = Field(None)
    devices: List[TaskDeviceBrief] = Field(default_factory=list)
    apis: List[TaskApiBrief] = Field(default_factory=list)
    source_tasks: List[TaskSourceBrief] = Field(default_factory=list)


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
    # INT-302/F3：本任务用例聚合的评估维度 [{id, name}]（重评估维度勾选候选集）
    evaluation_dimensions: List[Dict[str, Any]] = Field(default_factory=list)


class TaskDetailData(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    status: str = Field(...)
    # INT-301：任务级执行/评估双状态（评估推进只落评估侧，与执行完全分离）
    execution_status: Optional[str] = Field(None)
    evaluation_status: Optional[str] = Field(None)
    device_types: List[str] = Field(default_factory=list)
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
    # INT-301：task_progress 携带双状态，前端实时更新执行/评估双徽章
    execution_status: Optional[str] = Field(None)
    evaluation_status: Optional[str] = Field(None)
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


class TaskCaseDeviceAssignment(APIModel):
    """用例级被测设备选择（执行域 P0 新增）

    每个任务用例可独立指定被测设备类型与 ID（物理设备 / HTTP API / WebSocket API），
    为空时保持旧语义（按任务 type 路由）。device_type 取值见 DeviceType 枚举。
    """
    case_id: str = Field(...)
    device_type: Optional[str] = Field(None)
    device_id: Optional[str] = Field(None)
    lab_id: Optional[int] = Field(None)


class TaskCreateParameters(APIModel):
    case_ids: List[str] = Field(default_factory=list)
    device_ids: List[int] = Field(default_factory=list)
    api_ids: List[int] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class TaskCreateRequest(APIModel):
    name: str = Field(...)
    description: Optional[str] = Field(None)
    config: Optional[Dict[str, Any]] = Field(None)
    created_by: Optional[str] = Field(None)
    case_ids: Optional[List[str]] = Field(None)
    device_ids: Optional[List[int]] = Field(None)
    api_ids: Optional[List[int]] = Field(None)
    tags: Optional[List[str]] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    algorithm_params: Optional[Dict[str, Any]] = Field(None)
    case_devices: Optional[List[TaskCaseDeviceAssignment]] = Field(None)


class TaskControlRequest(APIModel):
    action: str = Field(...)
    case_id: Optional[int] = Field(None)


class TaskUpdateCasesRequest(APIModel):
    action: str = Field(...)
    case_ids: List[str] = Field(default_factory=list)


class TaskBatchActionRequest(APIModel):
    action: str = Field(...)
    task_ids: List[int] = Field(default_factory=list)


class TaskMergeRequest(APIModel):
    task_ids: List[int] = Field(default_factory=list)


class TaskListQuery(APIModel):
    page: int = Field(1)
    per_page: int = Field(10)
    status: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    search: Optional[str] = Field(None)
    start_date: Optional[str] = Field(None)
    end_date: Optional[str] = Field(None)
    # INT-141：favorite=true 仅当前用户收藏；deleted=true 仅回收站软删除项
    favorite: bool = Field(False)
    deleted: bool = Field(False)
    # INT-301：评估状态过滤（pending/evaluating/completed/failed/skipped，与执行状态并列）
    evaluation_status: Optional[str] = Field(None)
    # INT-298：merged=true 仅合并容器任务（对齐 V9.7.10 合并页签数据源）
    merged: bool = Field(False)
    # INT-301 F1：执行状态过滤（pending/queued/running/paused/completed/failed/
    # stopped/merged；复用派生表达式，徽章展示与筛选命中同口径）
    execution_status: Optional[str] = Field(None)


class TaskDomainStatsQuery(APIModel):
    """任务域全量聚合统计查询（GET /tasks/stats，INT-200）"""
    # 趋势分桶粒度（仅影响 trend）；非法值由 task_service 返回 error 透传为 400
    granularity: str = Field('day')


class TaskDomainStatsData(APIModel):
    """任务域全量聚合统计（统计卡 + 图表数据源，与列表筛选/分页无关）"""
    total: int = Field(..., description='未删除任务总数')
    deleted_total: int = Field(..., description='回收站（软删除）任务总数')
    status_counts: Dict[str, int] = Field(default_factory=dict, description='未删除任务按状态计数')
    type_counts: Dict[str, int] = Field(default_factory=dict, description='类型派生分布 api/e2e/mixed')
    trend: List[Dict[str, Any]] = Field(default_factory=list, description='完成任务按 created_at 分桶 [{key, count}]')
    granularity: str = Field('day', description='trend 分桶粒度 day/week/month/year')


class TaskBatchExportQuery(APIModel):
    format: str = Field('json')

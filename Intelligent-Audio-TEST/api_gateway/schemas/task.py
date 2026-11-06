from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
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


class TaskLabBrief(APIModel):
    """任务关联实验室简报（实验室扩展 INT-493/INT-540，多实验室 N:M）。

    内联于 TaskListItem / TaskDetailData 的 labs 字段，及 GET /tasks/{id}/labs 返回。
    """
    id: int = Field(...)
    code: str = Field(...)
    name: str = Field(...)


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
    # INT-339：挑选合并容器标记（task_cherry_pick_relations 存在性判定）
    is_cherry_pick: Optional[bool] = Field(None)
    # INT-577：统一合并容器「合并方式」（whole=整任务合并 / picked=结果挑选 / both）
    merge_type: Optional[str] = Field(None)
    # INT-577：容器来源任务数 / 来源结果数（列表次行「来源 {n} 任务 · 结果 {m} 条」）
    source_task_count: Optional[int] = Field(None)
    source_result_count: Optional[int] = Field(None)
    deleted: Optional[bool] = Field(None)
    deleted_at: Optional[str] = Field(None)
    deleted_by_user_id: Optional[int] = Field(None)
    # INT-423/466：资源可见性与归属人（前端徽标 + 路由层 owner 校验）
    visibility: Optional[str] = Field(None)
    created_by_user_id: Optional[int] = Field(None)
    reports: Optional[TaskReportsData] = Field(None)
    devices: List[TaskDeviceBrief] = Field(default_factory=list)
    apis: List[TaskApiBrief] = Field(default_factory=list)
    source_tasks: List[TaskSourceBrief] = Field(default_factory=list)
    # 实验室扩展（INT-493/INT-540）：任务关联实验室（多实验室 N:M，供「关联实验室」列）
    labs: List[TaskLabBrief] = Field(default_factory=list)


class TaskListData(PaginatedData[TaskListItem]):
    # INT-577：合并容器统计（merged=true ∪ cherry_pick=true 并集；供「挑选合并」页签计数/facet）
    stats: Optional[Dict[str, Any]] = Field(None)


class TaskCaseBrief(APIModel):
    case_id: str = Field(...)
    name: str = Field(...)
    status: Optional[str] = Field(None)
    execution_status: Optional[str] = Field(None)
    evaluation_status: Optional[str] = Field(None)
    started_at: Optional[str] = Field(None)
    completed_at: Optional[str] = Field(None)
    duration: Optional[float] = Field(None)
    # 用例真实轮次数（read model 取 config.rounds 长度）；任务详情「轮次」列分母
    rounds_count: Optional[int] = Field(None)
    error_message: Optional[str] = Field(None)
    group_name: Optional[str] = Field(None)
    tags: List[str] = Field(default_factory=list)
    # INT-302/F3：本任务用例聚合的评估维度 [{id, name}]（重评估维度勾选候选集）
    evaluation_dimensions: List[Dict[str, Any]] = Field(default_factory=list)
    # INT-340：该用例下是否存在人工复核结果（任务详情「人工复核」标记）
    # INT-734：DB 复核表无记录时上游可能透传 null，网关容错（缺省按 False/未复核）
    # INT-755：历史任务（reviewed 字段落地前创建）上游可能缺省该键 → None，
    # pydantic v2 显式拒绝 None 会 422，容错为 Optional（网关构造时归一 False）
    reviewed: Optional[bool] = Field(False)
    # 用例级执行目标数（同一用例 × 多 API/设备时，执行行收进 targets，不再重复出条）
    target_count: Optional[int] = Field(None)
    # 执行目标明细 [{task_case_id, device_type, device_id, api_id, status,
    # execution_status, evaluation_status, started_at, completed_at,
    # duration, error_message}]，供详情内逐目标对比
    targets: List[Dict[str, Any]] = Field(default_factory=list)


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
    # INT-340：任务下已复核结果条数（覆盖提醒）
    # INT-734：DB 复核表无记录时上游可能透传 null，网关容错（缺省 0）
    # INT-755：历史任务（INT-340 落地前创建）上游可能缺省该键 → None，
    # 与 reviewed 同族容错为 Optional（网关构造时归一 0，保持 int 契约）
    review_count: Optional[int] = Field(0)
    tags: List[str] = Field(default_factory=list)
    cases: List[TaskCaseBrief] = Field(default_factory=list)
    devices: List[TaskDeviceBrief] = Field(default_factory=list)
    apis: List[TaskApiBrief] = Field(default_factory=list)
    # 实验室扩展（INT-493/INT-540）：任务关联实验室（多实验室 N:M，信息格展示）
    labs: List[TaskLabBrief] = Field(default_factory=list)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)
    # INT-423/466：资源可见性与归属人（前端徽标 + 路由层 owner 校验）
    visibility: Optional[str] = Field(None)
    created_by_user_id: Optional[int] = Field(None)


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


class TargetModeItem(APIModel):
    """逐目标执行模式项（INT-1115 target_modes 契约 §5.2.4（一））。

    - target_type 见 TargetType 枚举（device/api）：target_id 分别命中
      device_ids（device）/ api_ids（api）；
    - mode 复用 ExecutionMode（parallel/serial）；
    - 列表顺序即串行链顺序（选中顺序；同类型道内相对顺序生效）。
    """
    target_type: str = Field(...)
    target_id: int = Field(...)
    mode: str = Field('parallel')

    @field_validator('target_type')
    @classmethod
    def _validate_target_type(cls, v):
        from shared.models.common_enums import TargetType
        if v not in tuple(item.value for item in TargetType):
            raise ValueError(f"target_type 合法值: {[item.value for item in TargetType]}")
        return v

    @field_validator('mode')
    @classmethod
    def _validate_mode(cls, v):
        from shared.models.common_enums import ExecutionMode
        if v not in tuple(item.value for item in ExecutionMode):
            raise ValueError(f"mode 合法值: {[item.value for item in ExecutionMode]}")
        return v


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
    # 实验室扩展（INT-493/INT-540）：关联实验室 ID 列表（可选，缺省=不限定实验室，兼容现状）
    lab_ids: Optional[List[int]] = Field(None)
    # INT-1115：逐目标执行模式（目标卡片级 并行/串行，§5.2.4）。列表顺序=选中顺序=
    # 串行链顺序；出现时必须恰好覆盖 device_ids ∪ api_ids 全部目标一次；缺省/空数组
    # = 全目标并行（现行为，零回归）。旧全局 execution_mode/serial_first 已废弃。
    target_modes: Optional[List[TargetModeItem]] = Field(None)
    # INT-566：新建任务可见性（shared/private；None 服务端默认 shared）
    visibility: Optional[str] = Field(None)

    @model_validator(mode='before')
    @classmethod
    def _reject_deprecated_execution_fields(cls, data):
        """提交旧字段 execution_mode/serial_first 一律 422（消息指明改用 target_modes）。

        旧 INT-604 全局执行模式字段已被 §5.2.4 逐目标 target_modes 契约取代；
        schema 不再声明这两个字段（extra="ignore" 不会自动拒绝），须在此显式拒绝。
        """
        if not isinstance(data, dict):
            return data
        deprecated = [k for k in (
            'execution_mode', 'executionMode', 'serial_first', 'serialFirst') if k in data]
        if deprecated:
            raise ValueError(
                f"已废弃字段 {'/'.join(deprecated)}：全局执行模式口径已废弃，"
                "请改用逐目标 target_modes（[{target_type, target_id, mode}]）")
        return data

    @model_validator(mode='after')
    def _validate_target_modes_coverage(self):
        """target_modes 校验：target_id 命中选中目标，且恰好覆盖全部选中目标一次。

        缺省/空数组 = 全目标并行，跳过校验（零回归）；违反即 422 并列出缺失/多余/重复。
        """
        target_modes = self.target_modes
        if not target_modes:
            return self
        selected = {('device', d) for d in (self.device_ids or [])} | \
                   {('api', a) for a in (self.api_ids or [])}

        seen = {}
        extra, duplicate = [], []
        for item in target_modes:
            key = (item.target_type, item.target_id)
            if key not in selected:
                extra.append(item)
            elif key in seen:
                duplicate.append(item)
            seen[key] = True
        missing = [key for key in selected if key not in seen]

        if missing or extra or duplicate:
            problems = []
            if missing:
                problems.append(f"缺失: {'、'.join(f'{t} {i}' for t, i in missing)}")
            if extra:
                problems.append(f"多余: {'、'.join(f'{it.target_type} {it.target_id}' for it in extra)}")
            if duplicate:
                problems.append(f"重复: {'、'.join(f'{it.target_type} {it.target_id}' for it in duplicate)}")
            raise ValueError(f"target_modes 必须恰好覆盖全部选中目标一次（{'; '.join(problems)}）")
        return self


class TaskValidateError(APIModel):
    """任务资源归属校验错误项（实验室扩展 INT-540 §4.5）。

    resource_type 取值：test_case / device / playback_device / laboratory。
    resource_id 保留资源原生 ID 类型（用例为字符串 ID，设备/播放设备/实验室为 int）。
    """
    resource_type: str = Field(...)
    resource_id: Union[int, str] = Field(...)
    reason: str = Field(...)


class TaskValidateData(APIModel):
    """任务资源归属校验结果（POST /api/tasks/validate，设计文档 §5.4.4）。"""
    valid: bool = Field(...)
    errors: List[TaskValidateError] = Field(default_factory=list)


class TaskValidateRequest(APIModel):
    """任务资源归属校验请求体（实验室扩展 INT-540 §4.5）。

    lab_ids 为空/缺省时：通用用例（config 无 lab_id）视为合法，
    专属用例/设备/播放设备因无归属实验室全部非法。
    playback_device_ids 可选：有值校验播放设备 lab_id 归属，无值跳过
    （当前系统任务无播放设备级关联，契约保留该可选字段）。
    """
    lab_ids: Optional[List[int]] = Field(None)
    case_ids: Optional[List[str]] = Field(None)
    device_ids: Optional[List[int]] = Field(None)
    playback_device_ids: Optional[List[int]] = Field(None)


class TaskCreateData(APIModel):
    """任务创建响应（实验室扩展 INT-540：响应内联 labs）。"""
    id: int = Field(...)
    labs: List[TaskLabBrief] = Field(default_factory=list)


class TaskLabsData(APIModel):
    """任务关联实验室查询响应（GET /api/tasks/{id}/labs，实验室扩展 INT-540）。"""
    task_id: int = Field(...)
    labs: List[TaskLabBrief] = Field(default_factory=list)


class TaskControlRequest(APIModel):
    action: str = Field(...)
    case_id: Optional[int] = Field(None)


class TaskUpdateCasesRequest(APIModel):
    action: str = Field(...)
    case_ids: List[str] = Field(default_factory=list)
    # 动态加用例的执行路由（device_type 必填；见 TaskCaseDeviceAssignment）
    case_devices: Optional[List[TaskCaseDeviceAssignment]] = Field(None)


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
    # INT-339：cherry_pick=true 仅挑选合并容器任务（专有关系表存在性判定，§5.4）
    cherry_pick: bool = Field(False)
    # INT-577：合并方式快捷筛选（whole|picked）——网关映射为 merged/cherry_pick 布尔；
    # 与 merged/cherry_pick 并存时以 merge_type 为准
    merge_type: Optional[str] = Field(None)
    # INT-577：返回合并容器统计块（merged ∪ cherry_pick 并集，供「挑选合并」页签计数/facet）
    stats: bool = Field(False)
    # INT-301 F1：执行状态过滤（pending/queued/running/paused/completed/failed/
    # stopped/merged；复用派生表达式，徽章展示与筛选命中同口径）
    execution_status: Optional[str] = Field(None)
    # INT-466：可见性筛选（shared/private；空=全部，走服务端行级过滤）
    visibility: Optional[str] = Field(None)


class TaskDomainStatsQuery(APIModel):
    """任务域全量聚合统计查询（GET /tasks/stats，INT-200）"""
    # 趋势分桶粒度（仅影响 trend）；非法值由 task_service 返回 error 透传为 400
    granularity: str = Field('day')


class TaskDomainStatsData(APIModel):
    """任务域全量聚合统计（统计卡 + 图表数据源，与列表筛选/分页无关）"""
    total: int = Field(..., description='未删除任务总数')
    deleted_total: int = Field(..., description='回收站（软删除）任务总数')
    status_counts: Dict[str, int] = Field(default_factory=dict, description='未删除任务按状态计数')
    trend: List[Dict[str, Any]] = Field(default_factory=list, description='完成任务按 created_at 分桶 [{key, count}]')
    granularity: str = Field('day', description='trend 分桶粒度 day/week/month/year')


class TaskBatchExportQuery(APIModel):
    format: str = Field('json')

from typing import Any, Dict, List, Optional
from pydantic import Field

from api_gateway.schemas.base import APIModel


class ReportMetricValue(APIModel):
    id: Optional[int] = Field(None)
    metric: str = Field(...)
    value: float = Field(...)


class ReportMetricValues(APIModel):
    metric: str = Field(...)
    values: List[float] = Field(default_factory=list)


class ReportRawDataGroup(APIModel):
    resource: str = Field(...)
    metrics: List[ReportMetricValues] = Field(default_factory=list)


class ReportMetricCategoryGroup(APIModel):
    category_id: str = Field(...)
    category_name: str = Field(...)
    metrics: List[ReportMetricValue] = Field(default_factory=list)


class ReportMetricByResource(APIModel):
    resource: str = Field(...)
    categories: List[ReportMetricCategoryGroup] = Field(default_factory=list)


class ReportTagMetricTagGroup(APIModel):
    tag_id: str = Field(...)
    tag_name: str = Field(...)
    category_id: Optional[int] = Field(None)
    category_name: Optional[str] = Field(None)
    metrics: List[ReportMetricValue] = Field(default_factory=list)


class ReportTagMetricByResource(APIModel):
    resource: str = Field(...)
    tags: List[ReportTagMetricTagGroup] = Field(default_factory=list)


class ReportTagCategoryMetric(APIModel):
    category_id: Optional[int] = Field(None)
    category_name: Optional[str] = Field(None)
    category_color: Optional[str] = Field(None)
    tags: List[ReportTagMetricTagGroup] = Field(default_factory=list)


class ReportTagCategoryMetricByResource(APIModel):
    resource: str = Field(...)
    categories: List[ReportTagCategoryMetric] = Field(default_factory=list)


class ReportCaseTypeStatGroup(APIModel):
    group_id: str = Field(...)
    group_name: str = Field(...)
    metrics: List[ReportMetricValue] = Field(default_factory=list)


class ReportDeviceStat(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    model: Optional[str] = Field(None)
    type: Optional[str] = Field(None)
    system: Optional[str] = Field(None)
    system_version: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    metrics: Optional[Dict[str, Any]] = Field(None)
    total_cases: int = Field(0)
    completed_cases: int = Field(0)
    failed_cases: int = Field(0)
    success_rate: float = Field(0)


class ReportApiStat(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    status: Optional[str] = Field(None)
    max_process: Optional[int] = Field(None)
    health_score: Optional[float] = Field(None)
    metrics: Optional[Dict[str, Any]] = Field(None)
    total_cases: int = Field(0)
    completed_cases: int = Field(0)
    failed_cases: int = Field(0)
    success_rate: float = Field(0)
    avg_response_time: Optional[float] = Field(None)
    stability: Optional[float] = Field(None)


class ReportDeviceInfo(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    model: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    type: Optional[str] = Field(None)
    system: Optional[str] = Field(None)
    system_version: Optional[str] = Field(None)
    app_name: Optional[str] = Field(None)
    app_version: Optional[str] = Field(None)
    location: Optional[str] = Field(None)
    max_audio_duration: Optional[float] = Field(None)
    needs_prompt_audio: Optional[bool] = Field(None)
    connection_type: Optional[str] = Field(None)
    keywords: Optional[str] = Field(None)
    serial_number: Optional[str] = Field(None)
    ip: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    last_online_at: Optional[str] = Field(None)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)

class ReportApiInfo(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    vendor: Optional[str] = Field(None)
    api_url: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    max_process: Optional[int] = Field(None)
    max_timeout: Optional[int] = Field(None)
    max_audio_duration: Optional[int] = Field(None)
    health_score: Optional[float] = Field(None)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class ReportResourceHeader(APIModel):
    key: str = Field(...)
    label: str = Field(...)
    type: Optional[str] = Field(None)
    id: Optional[int] = Field(None)
    name: Optional[str] = Field(None)
    version: Optional[str] = Field(None)
    editable: Optional[bool] = Field(None)


class ReportListItemSummary(APIModel):
    total_cases: int = Field(0)
    completed_cases: int = Field(0)
    failed_cases: int = Field(0)
    pass_rate: float = Field(0)
    # INT-340：人工复核条数（报告页「人工复核」标记）
    review_count: int = Field(0)
    task_count: Optional[int] = Field(None)


class ReportListItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    type: str = Field(...)
    task_id: Optional[int] = Field(None)
    task_name: str = Field(...)
    algorithm_type: Optional[str] = Field(None)
    summary: ReportListItemSummary = Field(default_factory=ReportListItemSummary)
    description: Optional[str] = Field(None)
    status: str = Field(...)
    created_at: str = Field(...)
    updated_at: Optional[str] = Field(None)
    # INT-141：收藏标记 / 回收站字段（INT-219：report 侧补齐，口径与 TaskListItem 一致）
    is_favorite: Optional[bool] = Field(None)
    deleted: Optional[bool] = Field(None)
    deleted_at: Optional[str] = Field(None)
    deleted_by_user_id: Optional[int] = Field(None)
    # INT-423/466：资源可见性与归属人（前端徽标 + 路由层 owner 校验）
    visibility: Optional[str] = Field(None)
    created_by_user_id: Optional[int] = Field(None)


class ReportListData(APIModel):
    items: List[ReportListItem] = Field(...)
    total: int = Field(...)
    page: int = Field(...)
    per_page: int = Field(...)
    pages: int = Field(...)


class ReportSummarySimplified(APIModel):
    raw_data: Any = Field(default_factory=dict)
    case_categories: List[Any] = Field(default_factory=list)
    all_case_tags: List[Any] = Field(default_factory=list)
    resources: List[Any] = Field(default_factory=list)
    resource_headers: List[ReportResourceHeader] = Field(default_factory=list)
    all_metrics: List[Any] = Field(default_factory=list)
    device_stats: List[ReportDeviceStat] = Field(default_factory=list)
    api_stats: List[ReportApiStat] = Field(default_factory=list)
    case_type_stats: Any = Field(default_factory=dict)
    devices: List[ReportDeviceInfo] = Field(default_factory=list)
    apis: List[ReportApiInfo] = Field(default_factory=list)
    metric_data: Any = Field(default_factory=dict)
    tag_metric_data: Any = Field(default_factory=dict)
    total_cases: int = Field(0)
    completed_cases: int = Field(0)
    failed_cases: int = Field(0)


class ReportDetailData(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    type: str = Field(...)
    task_id: Optional[int] = Field(None)
    task_type: Optional[str] = Field(None)
    task_name: str = Field(...)
    algorithm_type: Optional[str] = Field(None)
    summary: ReportSummarySimplified = Field(...)
    description: Optional[str] = Field(None)
    status: str = Field(...)
    analysis: Optional[str] = Field(None)
    created_at: str = Field(...)
    updated_at: Optional[str] = Field(None)
    # INT-219：回收站字段（详情序列化 _aggregate_to_dict 已输出，schema 口径对齐）
    deleted: Optional[bool] = Field(None)
    deleted_at: Optional[str] = Field(None)
    deleted_by_user_id: Optional[int] = Field(None)
    # INT-423/466：资源可见性与归属人（前端徽标 + 路由层 owner 校验）
    visibility: Optional[str] = Field(None)
    created_by_user_id: Optional[int] = Field(None)


class ReportIdData(APIModel):
    report_id: int = Field(...)


class IdData(APIModel):
    id: int = Field(...)


class ReportBatchDeleteRequest(APIModel):
    report_ids: List[int] = Field(..., max_length=100)


class ReportExportRequest(APIModel):
    ids: List[int] = Field(...)
    format: str = Field('csv')  # csv / excel / pdf / html


class ReportUpdateSummaryField(APIModel):
    case_categories: Optional[List[Any]] = Field(None)
    all_case_tags: Optional[List[Any]] = Field(None)
    all_tags: Optional[List[Any]] = Field(None)
    resource_headers: Optional[List[Any]] = Field(None)
    all_metrics: Optional[List[Any]] = Field(None)
    metric_data: Optional[Any] = Field(None)
    tag_metric_data: Optional[Any] = Field(None)
    raw_data: Optional[Any] = Field(None)
    device_stats: Optional[List[Any]] = Field(None)
    api_stats: Optional[List[Any]] = Field(None)
    case_type_stats: Optional[List[Any]] = Field(None)


class ReportUpdateRequest(APIModel):
    name: Optional[str] = Field(None)
    title: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    analysis: Optional[str] = Field(None)
    conclusion: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    summary: Optional[Dict[str, Any]] = Field(None)


class GenerateTaskReportRequest(APIModel):
    task_id: int = Field(...)
    name: Optional[str] = Field(None)
    description: Optional[str] = Field(None)


class CompareReportsRequest(APIModel):
    task_ids: List[int] = Field(...)
    name: Optional[str] = Field(None)
    description: Optional[str] = Field(None)


class SecondaryCompareRequest(APIModel):
    report_ids: List[int] = Field(...)
    description: Optional[str] = Field(None)


class GetCaseAveragesRequest(APIModel):
    task_id: Optional[int] = Field(None)
    report_id: Optional[int] = Field(None)
    category: Optional[str] = Field(None)
    tags: Optional[List[str]] = Field(None)
    categories: Optional[List[str]] = Field(None)
    include_untagged: Optional[bool] = Field(None)


class ReportListQuery(APIModel):
    page: int = Field(1)
    per_page: Optional[int] = Field(None)
    report_type: Optional[str] = Field(None, alias='type')
    status: Optional[str] = Field(None)
    # INT-262：按任务查报告（taskId/task_id 双拼写，经 NamingAliasMiddleware 补齐别名）
    task_id: Optional[int] = Field(None)
    keyword: Optional[str] = Field(None)
    start_time: Optional[str] = Field(None)
    end_time: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    sort_by: str = Field('created_at')
    order: str = Field('desc')
    # INT-141：favorite=true 仅当前用户收藏；deleted=true 仅回收站软删除项
    favorite: bool = Field(False)
    deleted: bool = Field(False)


class ReportCaseListQuery(APIModel):
    page: int = Field(1)
    per_page: int = Field(20)
    keyword: Optional[str] = Field(None)
    category: Optional[str] = Field(None)
    tags: Optional[List[str]] = Field(None)


class ReportSearchCasesRequest(APIModel):
    keyword: Optional[str] = Field(None)
    category: Optional[str] = Field(None)
    # 多分类筛选（与 category 单分类并存，categories 有值时按 IN 过滤）
    categories: Optional[List[str]] = Field(None)
    include_untagged: Optional[bool] = Field(None)
    tags: Optional[List[str]] = Field(None)
    # 按指标名筛选（case 的 metrics 中包含该指标名）
    metrics: Optional[List[str]] = Field(None)
    # 排序字段：name/category/createdat/metric
    sort_by: Optional[str] = Field('name')
    # 当 sort_by='metric' 时指定按哪个指标排序
    sort_metric: Optional[str] = Field(None)
    # 当 sort_by='metric' 时限定排序用的资源（设备/API 名），缺省聚合所有资源
    sort_resource: Optional[str] = Field(None)
    # 排序方向 asc/desc
    sort_order: Optional[str] = Field('asc')
    page: int = Field(1)
    per_page: int = Field(20)


class ReportExportQuery(APIModel):
    ids: str = Field('')
    format: str = Field('csv')


# ===== 报告统计分析（INT-791：G04 报告统计分析页） =====


class ReportStatisticsQuery(APIModel):
    """GET /reports/statistics 查询参数。"""
    # 统计维度：time | task_type | device_type | evaluation_metric
    dimension: str = Field('time')
    start_time: Optional[str] = Field(None)
    end_time: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)


class ReportStatisticsTrendQuery(APIModel):
    """GET /reports/statistics/trend 查询参数。"""
    # 趋势类型：time | dimension
    trend_type: str = Field('time')
    metric: Optional[str] = Field(None)
    start_time: Optional[str] = Field(None)
    end_time: Optional[str] = Field(None)


class StatisticsReportTimeRange(APIModel):
    """POST /reports/statistics/report 时间范围。"""
    start_time: Optional[str] = Field(None)
    end_time: Optional[str] = Field(None)


class GenerateStatisticsReportRequest(APIModel):
    """POST /reports/statistics/report 请求体。"""
    # 报表类型：report_count | case_execution | evaluation_metric | device_performance
    report_type: str = Field('report_count')
    # 报表内容（可空，§2.2 口径，预留扩展）
    content: Optional[str] = Field(None)
    # 格式：csv | excel | pdf | html
    format: str = Field('csv')
    time_range: StatisticsReportTimeRange = Field(default_factory=StatisticsReportTimeRange)


# ===== 报告分享（INT-971：生成 / 列表 / 撤销 / 公开读取） =====


class ReportShareCreateRequest(APIModel):
    """POST /reports/{report_id}/share 请求体。"""
    # 访问口径：login | specific | public
    access: str = Field('login')
    # 有效期：none | 7d | 30d | custom
    expiry: str = Field('none')
    # 仅 expiry=custom 必填（ISO 8601，如 2026-10-30T00:00:00Z）
    expires_at: Optional[str] = Field(None)
    # 空串 = 不设密码
    password: Optional[str] = Field(None)
    # 仅 access=specific；逗号分隔用户名/邮箱（网关经 auth ListUsers 解析）
    recipients: Optional[str] = Field(None)

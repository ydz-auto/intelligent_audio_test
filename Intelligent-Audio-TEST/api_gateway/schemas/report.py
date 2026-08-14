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


class ReportIdData(APIModel):
    report_id: int = Field(...)


class IdData(APIModel):
    id: int = Field(...)


class ReportBatchDeleteRequest(APIModel):
    report_ids: List[int] = Field(..., max_length=100)


class ReportExportRequest(APIModel):
    ids: List[int] = Field(...)
    format: str = Field('csv')


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
    task_id: int = Field(...)
    category: Optional[str] = Field(None)
    tags: Optional[List[str]] = Field(None)
    categories: Optional[List[str]] = Field(None)
    include_untagged: Optional[bool] = Field(None)


class ReportListQuery(APIModel):
    page: int = Field(1)
    per_page: Optional[int] = Field(None)
    report_type: Optional[str] = Field(None, alias='type')
    status: Optional[str] = Field(None)
    keyword: Optional[str] = Field(None)
    start_time: Optional[str] = Field(None)
    end_time: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    sort_by: str = Field('created_at')
    order: str = Field('desc')


class ReportCaseListQuery(APIModel):
    page: int = Field(1)
    per_page: int = Field(20)
    keyword: Optional[str] = Field(None)
    category: Optional[str] = Field(None)
    tags: Optional[List[str]] = Field(None)


class ReportSearchCasesRequest(APIModel):
    keyword: Optional[str] = Field(None)
    category: Optional[str] = Field(None)
    include_untagged: Optional[bool] = Field(None)
    tags: Optional[List[str]] = Field(None)
    page: int = Field(1)
    per_page: int = Field(20)

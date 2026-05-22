from typing import Any, Dict, List, Optional
from pydantic import Field, AliasChoices

from backend.schemas.base import APIModel


class ReportMetricValue(APIModel):
    id: Optional[int] = Field(None, alias='id', validation_alias='id')
    metric: str = Field(..., alias='metric', validation_alias='metric')
    value: float = Field(..., alias='value', validation_alias='value')


class ReportMetricValues(APIModel):
    metric: str = Field(..., alias='metric', validation_alias='metric')
    values: List[float] = Field(default_factory=list, alias='values', validation_alias='values')


class ReportRawDataGroup(APIModel):
    resource: str = Field(..., alias='resource', validation_alias='resource')
    metrics: List[ReportMetricValues] = Field(default_factory=list, alias='metrics', validation_alias='metrics')


class ReportMetricCategoryGroup(APIModel):
    category_id: str = Field(..., alias='categoryId', validation_alias='categoryId')
    category_name: str = Field(..., alias='categoryName', validation_alias='categoryName')
    metrics: List[ReportMetricValue] = Field(default_factory=list, alias='metrics', validation_alias='metrics')


class ReportMetricByResource(APIModel):
    resource: str = Field(..., alias='resource', validation_alias='resource')
    categories: List[ReportMetricCategoryGroup] = Field(default_factory=list, alias='categories', validation_alias='categories')


class ReportTagMetricTagGroup(APIModel):
    tag_id: str = Field(..., alias='tagId', validation_alias='tagId')
    tag_name: str = Field(..., alias='tagName', validation_alias='tagName')
    category_id: Optional[int] = Field(None, alias='categoryId', validation_alias=AliasChoices('category_id', 'categoryId'))
    category_name: Optional[str] = Field(None, alias='categoryName', validation_alias=AliasChoices('category_name', 'categoryName'))
    metrics: List[ReportMetricValue] = Field(default_factory=list, alias='metrics', validation_alias='metrics')


class ReportTagMetricByResource(APIModel):
    resource: str = Field(..., alias='resource', validation_alias='resource')
    tags: List[ReportTagMetricTagGroup] = Field(default_factory=list, alias='tags', validation_alias='tags')


class ReportTagCategoryMetric(APIModel):
    category_id: Optional[int] = Field(None, alias='categoryId', validation_alias=AliasChoices('category_id', 'categoryId'))
    category_name: Optional[str] = Field(None, alias='categoryName', validation_alias=AliasChoices('category_name', 'categoryName'))
    category_color: Optional[str] = Field(None, alias='categoryColor', validation_alias=AliasChoices('category_color', 'categoryColor'))
    tags: List[ReportTagMetricTagGroup] = Field(default_factory=list, alias='tags', validation_alias='tags')


class ReportTagCategoryMetricByResource(APIModel):
    resource: str = Field(..., alias='resource', validation_alias='resource')
    categories: List[ReportTagCategoryMetric] = Field(default_factory=list, alias='categories', validation_alias='categories')


class ReportCaseTypeStatGroup(APIModel):
    group_id: str = Field(..., alias='groupId', validation_alias='groupId')
    group_name: str = Field(..., alias='groupName', validation_alias='groupName')
    metrics: List[ReportMetricValue] = Field(default_factory=list, alias='metrics', validation_alias='metrics')


class ReportDeviceStat(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    model: Optional[str] = Field(None, alias='model', validation_alias='model')
    type: Optional[str] = Field(None, alias='type', validation_alias='type')
    system: Optional[str] = Field(None, alias='system', validation_alias='system')
    system_version: Optional[str] = Field(None, alias='systemVersion', validation_alias=AliasChoices('system_version', 'systemVersion'))
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    metrics: Optional[Dict[str, Any]] = Field(None, alias='metrics', validation_alias='metrics')
    total_cases: int = Field(0, alias='totalCases', validation_alias=AliasChoices('total_cases', 'totalCases'))
    completed_cases: int = Field(0, alias='completedCases', validation_alias=AliasChoices('completed_cases', 'completedCases'))
    failed_cases: int = Field(0, alias='failedCases', validation_alias=AliasChoices('failed_cases', 'failedCases'))
    success_rate: float = Field(0, alias='successRate', validation_alias=AliasChoices('success_rate', 'successRate'))


class ReportApiStat(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    max_process: Optional[int] = Field(None, alias='maxProcess', validation_alias=AliasChoices('max_process', 'maxProcess'))
    health_score: Optional[float] = Field(None, alias='healthScore', validation_alias=AliasChoices('health_score', 'healthScore'))
    metrics: Optional[Dict[str, Any]] = Field(None, alias='metrics', validation_alias='metrics')
    total_cases: int = Field(0, alias='totalCases', validation_alias=AliasChoices('total_cases', 'totalCases'))
    completed_cases: int = Field(0, alias='completedCases', validation_alias=AliasChoices('completed_cases', 'completedCases'))
    failed_cases: int = Field(0, alias='failedCases', validation_alias=AliasChoices('failed_cases', 'failedCases'))
    success_rate: float = Field(0, alias='successRate', validation_alias=AliasChoices('success_rate', 'successRate'))
    avg_response_time: Optional[float] = Field(None, alias='avgResponseTime', validation_alias=AliasChoices('avg_response_time', 'avgResponseTime'))
    stability: Optional[float] = Field(None, alias='stability', validation_alias='stability')


class ReportDeviceInfo(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    model: Optional[str] = Field(None, alias='model', validation_alias='model')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    type: Optional[str] = Field(None, alias='type', validation_alias='type')
    system: Optional[str] = Field(None, alias='system', validation_alias='system')
    system_version: Optional[str] = Field(None, alias='systemVersion', validation_alias='systemVersion')
    app_name: Optional[str] = Field(None, alias='appName', validation_alias='appName')
    app_version: Optional[str] = Field(None, alias='appVersion', validation_alias='appVersion')
    location: Optional[str] = Field(None, alias='location', validation_alias='location')
    max_audio_duration: Optional[float] = Field(None, alias='maxAudioDuration', validation_alias='maxAudioDuration')
    needs_prompt_audio: Optional[bool] = Field(None, alias='needsPromptAudio', validation_alias='needsPromptAudio')
    connection_type: Optional[str] = Field(None, alias='connectionType', validation_alias='connectionType')
    keywords: Optional[str] = Field(None, alias='keywords', validation_alias='keywords')
    serial_number: Optional[str] = Field(None, alias='serialNumber', validation_alias='serialNumber')
    ip: Optional[str] = Field(None, alias='ip', validation_alias='ip')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    last_online_at: Optional[str] = Field(None, alias='lastOnlineAt', validation_alias='lastOnlineAt')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')

class ReportApiInfo(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    vendor: Optional[str] = Field(None, alias='vendor', validation_alias='vendor')
    api_url: Optional[str] = Field(None, alias='apiUrl', validation_alias='apiUrl')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    max_process: Optional[int] = Field(None, alias='maxProcess', validation_alias='maxProcess')
    max_timeout: Optional[int] = Field(None, alias='maxTimeout', validation_alias='maxTimeout')
    max_audio_duration: Optional[int] = Field(None, alias='maxAudioDuration', validation_alias='maxAudioDuration')
    health_score: Optional[float] = Field(None, alias='healthScore', validation_alias='healthScore')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')


class ReportResourceHeader(APIModel):
    key: str = Field(..., alias='key', validation_alias='key')
    label: str = Field(..., alias='label', validation_alias='label')
    type: Optional[str] = Field(None, alias='type', validation_alias='type')
    id: Optional[int] = Field(None, alias='id', validation_alias='id')
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    version: Optional[str] = Field(None, alias='version', validation_alias='version')
    editable: Optional[bool] = Field(None, alias='editable', validation_alias='editable')


class ReportListItemSummary(APIModel):
    total_cases: int = Field(0, alias='totalCases', validation_alias='totalCases')
    completed_cases: int = Field(0, alias='completedCases', validation_alias='completedCases')
    failed_cases: int = Field(0, alias='failedCases', validation_alias='failedCases')
    pass_rate: float = Field(0, alias='passRate', validation_alias='passRate')
    task_count: Optional[int] = Field(None, alias='taskCount', validation_alias='taskCount')


class ReportListItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    type: str = Field(..., alias='type', validation_alias='type')
    task_id: Optional[int] = Field(None, alias='taskId', validation_alias='taskId')
    task_name: str = Field(..., alias='taskName', validation_alias='taskName')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    summary: ReportListItemSummary = Field(default_factory=ReportListItemSummary, alias='summary', validation_alias='summary')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    status: str = Field(..., alias='status', validation_alias='status')
    created_at: str = Field(..., alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')


class ReportListData(APIModel):
    items: List[ReportListItem] = Field(..., alias='items', validation_alias='items')
    total: int = Field(..., alias='total', validation_alias='total')
    page: int = Field(..., alias='page', validation_alias='page')
    per_page: int = Field(..., alias='perPage', validation_alias='perPage')
    pages: int = Field(..., alias='pages', validation_alias='pages')


class ReportSummarySimplified(APIModel):
    raw_data: Any = Field(default_factory=dict, alias='rawData', validation_alias=AliasChoices('raw_data', 'rawData'))
    case_categories: List[Any] = Field(default_factory=list, alias='caseCategories', validation_alias=AliasChoices('case_categories', 'caseCategories'))
    all_case_tags: List[Any] = Field(default_factory=list, alias='allCaseTags', validation_alias=AliasChoices('all_case_tags', 'allCaseTags'))
    resources: List[Any] = Field(default_factory=list, alias='resources', validation_alias=AliasChoices('resources'))
    resource_headers: List[ReportResourceHeader] = Field(default_factory=list, alias='resourceHeaders', validation_alias=AliasChoices('resource_headers', 'resourceHeaders'))
    all_metrics: List[Any] = Field(default_factory=list, alias='allMetrics', validation_alias=AliasChoices('all_metrics', 'allMetrics'))
    device_stats: List[ReportDeviceStat] = Field(default_factory=list, alias='deviceStats', validation_alias=AliasChoices('device_stats', 'deviceStats'))
    api_stats: List[ReportApiStat] = Field(default_factory=list, alias='apiStats', validation_alias=AliasChoices('api_stats', 'apiStats'))
    case_type_stats: List[ReportCaseTypeStatGroup] = Field(default_factory=list, alias='caseTypeStats', validation_alias=AliasChoices('case_type_stats', 'caseTypeStats'))
    devices: List[ReportDeviceInfo] = Field(default_factory=list, alias='devices', validation_alias=AliasChoices('devices'))
    apis: List[ReportApiInfo] = Field(default_factory=list, alias='apis', validation_alias=AliasChoices('apis'))
    cases: List[Any] = Field(default_factory=list, alias='cases', validation_alias=AliasChoices('cases'))
    metric_data: Any = Field(default_factory=dict, alias='metricData', validation_alias=AliasChoices('metric_data', 'metricData'))
    tag_metric_data: Any = Field(default_factory=dict, alias='tagMetricData', validation_alias=AliasChoices('tag_metric_data', 'tagMetricData'))
    total_cases: int = Field(0, alias='totalCases', validation_alias=AliasChoices('total_cases', 'totalCases'))
    completed_cases: int = Field(0, alias='completedCases', validation_alias=AliasChoices('completed_cases', 'completedCases'))
    failed_cases: int = Field(0, alias='failedCases', validation_alias=AliasChoices('failed_cases', 'failedCases'))


class ReportDetailData(APIModel):
    id: int = Field(..., alias='id', validation_alias=AliasChoices('id'))
    name: str = Field(..., alias='name', validation_alias=AliasChoices('name'))
    type: str = Field(..., alias='type', validation_alias=AliasChoices('type'))
    task_id: Optional[int] = Field(None, alias='taskId', validation_alias=AliasChoices('task_id', 'taskId'))
    task_type: Optional[str] = Field(None, alias='taskType', validation_alias=AliasChoices('task_type', 'taskType'))
    task_name: str = Field(..., alias='taskName', validation_alias=AliasChoices('task_name', 'taskName'))
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias=AliasChoices('algorithm_type', 'algorithmType'))
    summary: ReportSummarySimplified = Field(..., alias='summary', validation_alias=AliasChoices('summary'))
    description: Optional[str] = Field(None, alias='description', validation_alias=AliasChoices('description'))
    status: str = Field(..., alias='status', validation_alias=AliasChoices('status'))
    analysis: Optional[str] = Field(None, alias='analysis', validation_alias=AliasChoices('analysis'))
    created_at: str = Field(..., alias='createdAt', validation_alias=AliasChoices('created_at', 'createdAt'))
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias=AliasChoices('updated_at', 'updatedAt'))


class ReportIdData(APIModel):
    report_id: int = Field(..., alias='reportId', validation_alias='reportId')


class IdData(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')


class ReportBatchDeleteRequest(APIModel):
    report_ids: List[int] = Field(..., alias='reportIds', validation_alias='reportIds', max_length=100)


class ReportExportRequest(APIModel):
    ids: List[int] = Field(..., alias='ids', validation_alias='ids')
    format: str = Field('csv', alias='format', validation_alias='format')


class ReportUpdateSummaryField(APIModel):
    case_categories: Optional[List[Any]] = Field(None, alias='caseCategories', validation_alias='caseCategories')
    all_case_tags: Optional[List[Any]] = Field(None, alias='allCaseTags', validation_alias='allCaseTags')
    all_tags: Optional[List[Any]] = Field(None, alias='allTags', validation_alias='allTags')
    resource_headers: Optional[List[Any]] = Field(None, alias='resourceHeaders', validation_alias='resourceHeaders')
    all_metrics: Optional[List[Any]] = Field(None, alias='allMetrics', validation_alias='allMetrics')
    metric_data: Optional[Any] = Field(None, alias='metricData', validation_alias='metricData')
    tag_metric_data: Optional[Any] = Field(None, alias='tagMetricData', validation_alias='tagMetricData')
    raw_data: Optional[Any] = Field(None, alias='rawData', validation_alias='rawData')
    device_stats: Optional[List[Any]] = Field(None, alias='deviceStats', validation_alias='deviceStats')
    api_stats: Optional[List[Any]] = Field(None, alias='apiStats', validation_alias='apiStats')
    case_type_stats: Optional[List[Any]] = Field(None, alias='caseTypeStats', validation_alias='caseTypeStats')


class ReportUpdateRequest(APIModel):
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    title: Optional[str] = Field(None, alias='title', validation_alias='title')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    analysis: Optional[str] = Field(None, alias='analysis', validation_alias='analysis')
    conclusion: Optional[str] = Field(None, alias='conclusion', validation_alias='conclusion')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    summary: Optional[Dict[str, Any]] = Field(None, alias='summary', validation_alias='summary')


class GenerateTaskReportRequest(APIModel):
    task_id: int = Field(..., alias='taskId', validation_alias='taskId')
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')


class CompareReportsRequest(APIModel):
    task_ids: List[int] = Field(..., alias='taskIds', validation_alias='taskIds')
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')


class SecondaryCompareRequest(APIModel):
    report_ids: List[int] = Field(..., alias='reportIds', validation_alias='reportIds')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')


class GetCaseAveragesRequest(APIModel):
    task_id: int = Field(..., alias='taskId', validation_alias='taskId')
    category: Optional[str] = Field(None, alias='category', validation_alias='category')
    tags: Optional[List[str]] = Field(None, alias='tags', validation_alias='tags')
    categories: Optional[List[str]] = Field(None, alias='categories', validation_alias='categories')
    include_untagged: Optional[bool] = Field(None, alias='includeUntagged', validation_alias='includeUntagged')


class ReportListQuery(APIModel):
    page: int = Field(1, alias='page', validation_alias='page')
    per_page: Optional[int] = Field(None, alias='perPage', validation_alias='perPage')
    report_type: Optional[str] = Field(None, alias='type', validation_alias='type')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    keyword: Optional[str] = Field(None, alias='keyword', validation_alias='keyword')
    start_time: Optional[str] = Field(None, alias='startTime', validation_alias='startTime')
    end_time: Optional[str] = Field(None, alias='endTime', validation_alias='endTime')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    sort_by: str = Field('created_at', alias='sortBy', validation_alias='sortBy')
    order: str = Field('desc', alias='order', validation_alias='order')


class ReportCaseListQuery(APIModel):
    page: int = Field(1, alias='page', validation_alias='page')
    per_page: int = Field(20, alias='perPage', validation_alias='perPage')
    keyword: Optional[str] = Field(None, alias='keyword', validation_alias='keyword')
    category: Optional[str] = Field(None, alias='category', validation_alias='category')
    tags: Optional[List[str]] = Field(None, alias='tags', validation_alias='tags')


class ReportSearchCasesRequest(APIModel):
    keyword: Optional[str] = Field(None, alias='keyword', validation_alias='keyword')
    category: Optional[str] = Field(None, alias='category', validation_alias='category')
    include_untagged: Optional[bool] = Field(None, alias='includeUntagged', validation_alias='includeUntagged')
    tags: Optional[List[str]] = Field(None, alias='tags', validation_alias='tags')
    page: int = Field(1, alias='page', validation_alias='page')
    per_page: int = Field(20, alias='perPage', validation_alias='perPage')

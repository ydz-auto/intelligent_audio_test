/**
 * Report DTO —— snake_case
 * 与后端 api_gateway/schemas/report.py 一一对应（serialize_by_alias=False 输出 snake_case）。
 *
 * 关键契约（已校准）：
 * - 列表 ReportListItem = {id, name, type, task_id, task_name, algorithm_type, summary, description, status, created_at, updated_at}
 * - 详情 GET /reports/{id} 返回 report_service 聚合根 _aggregate_to_dict：
 *   {id, task_id, report_type, status, config, created_at, summaries[], cases[], metric_stats[], raw_data[]}
 * - Enum 值不转换（report_type/status 保持后端原值），仅字段名 snake_case。
 */

// ===== 指标与统计 =====

/** 指标配置（summary.all_metrics 元素） */
export interface ReportMetricConfigDto {
  id?: string | number
  name: string
  unit?: string
  decimal_places?: number
  statistic_method?: string
  dimension_type?: string
  parent_dimension_id?: number | string | null
  parent_dimension_name?: string | null
}

/** 指标单值 */
export interface ReportMetricValueDto {
  id?: number | null
  metric: string
  value: number
}

/** 指标多值（raw_data 组内元素） */
export interface ReportMetricValuesDto {
  metric: string
  values: number[]
}

/** 原始数据分组（flatten_raw_data 输出） */
export interface ReportRawDataGroupDto {
  resource: string
  metrics: ReportMetricValuesDto[]
}

/** 分类 × 指标均值组（metric_data.categories 元素） */
export interface ReportMetricCategoryGroupDto {
  category_id: string
  category_name: string
  metrics: ReportMetricValueDto[]
}

/** 分类 × 资源指标矩阵（metric_data 元素） */
export interface ReportMetricByResourceDto {
  resource: string
  categories: ReportMetricCategoryGroupDto[]
}

/** 标签 × 指标均值组（tag_metric_data.tags 元素；后端含可选 category 冗余） */
export interface ReportTagMetricTagGroupDto {
  tag_id: string
  tag_name: string
  category_id?: number | null
  category_name?: string | null
  metrics: ReportMetricValueDto[]
}

/** 标签 × 资源指标矩阵（tag_metric_data 元素） */
export interface ReportTagMetricByResourceDto {
  resource: string
  tags: ReportTagMetricTagGroupDto[]
}

/** 用例类型统计行（case_type_stats 元素） */
export interface ReportCaseTypeStatRowDto {
  group_id: string
  group_name: string
  metrics: ReportMetricValueDto[]
}

/** 详情设备统计（ReportDeviceStat） */
export interface ReportDeviceStatDto {
  id: number
  name: string
  model?: string | null
  type?: string | null
  system?: string | null
  system_version?: string | null
  status?: string | null
  metrics?: Record<string, number> | null
  total_cases: number
  completed_cases: number
  failed_cases: number
  success_rate: number
}

/** 详情 API 统计（ReportApiStat） */
export interface ReportApiStatDto {
  id: number
  name: string
  status?: string | null
  max_process?: number | null
  health_score?: number | null
  metrics?: Record<string, number> | null
  total_cases: number
  completed_cases: number
  failed_cases: number
  success_rate: number
  avg_response_time?: number | null
  stability?: number | null
}

/** 详情设备信息（ReportDeviceInfo） */
export interface ReportDeviceInfoDto {
  id: number
  name: string
  model?: string | null
  description?: string | null
  type?: string | null
  system?: string | null
  system_version?: string | null
  app_name?: string | null
  app_version?: string | null
  location?: string | null
  max_audio_duration?: number | null
  needs_prompt_audio?: boolean | null
  connection_type?: string | null
  keywords?: string | null
  serial_number?: string | null
  ip?: string | null
  status?: string | null
  last_online_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

/** 详情 API 信息（ReportApiInfo） */
export interface ReportApiInfoDto {
  id: number
  name: string
  vendor?: string | null
  api_url?: string | null
  description?: string | null
  status?: string | null
  max_process?: number | null
  max_timeout?: number | null
  max_audio_duration?: number | null
  health_score?: number | null
  created_at?: string | null
  updated_at?: string | null
}

/** 资源表头（ReportResourceHeader） */
export interface ReportResourceHeaderDto {
  key: string
  label: string
  type?: string | null
  id?: number | null
  name?: string | null
  version?: string | null
  editable?: boolean | null
}

/** 列表项摘要统计（ReportListItemSummary） */
export interface ReportListItemSummaryDto {
  total_cases: number
  completed_cases: number
  failed_cases: number
  pass_rate: number
  task_count?: number | null
}

/** 列表项（ReportListItem） */
export interface ReportListItemDto {
  id: number
  name: string
  type: string
  task_id?: number | null
  task_name: string
  algorithm_type?: string | null
  summary: ReportListItemSummaryDto
  description?: string | null
  status: string
  created_at: string
  updated_at?: string | null
}

/** 列表响应（ReportListData） */
export interface ReportListDataDto {
  items: ReportListItemDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

// ===== 详情侧 =====

/**
 * 报告详情摘要（summary）—— snake_case DTO。
 *
 * 注意：
 * - ReportSummarySimplified（网关详情 schema）中 raw_data/metric_data/tag_metric_data/case_type_stats
 *   为 Any（dict 或 list 视聚合来源而定），此处以数组形状为准，adapter 对非数组容忍为空。
 * - metrics/dimension_values 的键为数据 key（维度名/分类名等）而非字段名，保留 Record。
 */
export interface ReportSummaryDto {
  total_cases: number
  completed_cases: number
  failed_cases: number
  passed_cases?: number
  pass_rate?: number
  avg_score?: number
  all_metrics?: ReportMetricConfigDto[]
  /** 用例维度明细（后端历史形状不稳定，宽松可选；键名不做 snake/camel 转换） */
  detailed_results?: Array<Record<string, unknown>>
  device_stats?: ReportDeviceStatDto[]
  api_stats?: ReportApiStatDto[]
  /** 分类 × 指标均值（键为数据 key 非字段名） */
  metrics?: Record<string, number>
  rawDataGroup?: never
  raw_data?: ReportRawDataGroupDto[]
  metric_data?: ReportMetricByResourceDto[]
  tag_metric_data?: ReportTagMetricByResourceDto[]
  case_type_stats?: ReportCaseTypeStatRowDto[]
  overall_success_rate?: number
  stability?: number
  /** 维度名 → 值（键为维度名非字段名） */
  dimension_values?: Record<string, number>
  devices?: Array<string | ReportDeviceInfoDto>
  apis?: Array<string | ReportApiInfoDto>
  resource_headers?: ReportResourceHeaderDto[]
  case_categories?: string[]
  all_case_tags?: string[]
  /** 兼容旧字段（与 all_case_tags 并存，后端遗留） */
  all_tags?: string[]
  resources?: string[]
  field_mappings?: Record<string, unknown>
}

/** 用例维度明细（detailed_results 元素；历史键名混用，宽松可选） */
export interface DetailedResultDto {
  id: string | number
  case_name?: string
  score?: number
  result?: string
  execution_status?: string
  test_case_id?: string | number
  test_case_name?: string
  device_name?: string
  api_name?: string
  audio_name?: string
  created_at?: string
  error_message?: string
}

/**
 * 报告 DTO（统一列表/详情）。
 * - 列表项：ReportListItemDto（summary 为列表摘要统计）
 * - 详情项：聚合根形状 + summary（ReportSummaryDto），name/task_name/title 兼容展示字段来自 config JSON
 */
export interface ReportDto {
  id: string | number
  /** 列表来自 name 列；详情来自 config.name，缺失回退 title/空串 */
  name: string
  /** 报告类型后端原值（task/comparison/secondary_comparison/standard） */
  type: string
  status: string
  created_at: string
  updated_at?: string | null
  task_id?: string | number | null
  /** 列表/对比报告聚合输出；详情聚合根无此字段 */
  task_name?: string
  algorithm_type?: string | null
  description?: string | null
  summary?: ReportSummaryDto
  detailed_results?: DetailedResultDto[]
  conclusion?: string | null
  /** 报告编辑标题（ReportUpdateRequest.title） */
  title?: string
  /** 聚合根 config JSON（键为数据 key 非字段名） */
  config?: Record<string, unknown>
  /** 详情聚合根 summaries[]（摘要元数据行） */
  summaries?: Array<{
    id: number
    report_id: number
    metric_name: string
    metric_value: number
    metadata: Record<string, unknown>
  }>
  /** 详情聚合根 cases[] */
  cases?: Array<{
    id: number
    report_id: number
    test_case_id: string
    result_summary: Record<string, unknown>
    score?: number | null
  }>
  /** 详情聚合根 metric_stats[] */
  metric_stats?: Array<{
    id: number
    report_id: number
    metric_name: string
    avg: number
    min: number
    max: number
    std_dev: number
    sample_count: number
  }>
  /** 详情聚合根 raw_data[]（原始数据子实体；注意与 summary.raw_data 分组结构不同名冲突——分属两个接口） */
  raw_data?: Array<{
    id: number
    report_id: number
    data_type: string
    data: Record<string, unknown>
  }>
}

/** 报告对比结果（compare/secondary-compare 响应，Enum 值不转换） */
export interface CompareResultDto {
  /** 生成的报告 ID（compare） */
  report_id?: string | number
  /** 兼容旧响应字段 */
  id?: string | number
  /** 二次对比返回的 key 列表 */
  report_key?: Array<string | number>
  /** 生成状态（exists/generating/completed） */
  status?: string
  /** 差异描述（预留） */
  differences?: unknown[]
}

/** 报告列表查询参数（ReportListQuery → snake_case 请求参数） */
export interface ReportListQueryDto {
  page: number
  per_page: number
  sort_by: string
  order: 'asc' | 'desc'
  /** 报告类型过滤（后端 query 别名 type → report_type） */
  report_type?: string
  status?: string
  keyword?: string
  start_time?: string
  end_time?: string
  algorithm_type?: string
}

/** 报告更新请求体（ReportUpdateRequest） */
export interface ReportUpdateDto {
  name?: string
  title?: string
  description?: string
  analysis?: string
  conclusion?: string
  status?: string
  summary?: Record<string, unknown>
}

/** 生成任务报告请求体（GenerateTaskReportRequest） */
export interface GenerateTaskReportDto {
  task_id: number | string
  name?: string | null
  description?: string | null
}

/** 批量删除请求体（后端 batch_delete 直接 body.get('ids')，非 schema） */
export interface ReportBatchDeleteDto {
  ids: Array<string | number>
  hard_delete?: boolean
}

/** 报告导出请求体（ReportExportRequest） */
export interface ReportExportDto {
  ids: Array<string | number>
  format: string
}

/** 用例平均值查询请求体（GetCaseAveragesRequest） */
export interface GetCaseAveragesDto {
  task_id: string | number
  category?: string | null
  tags?: string[]
  categories?: string[]
  include_untagged?: boolean | null
}

/** 报告用例列表查询参数（ReportCaseListQuery） */
export interface ReportCaseListQueryDto {
  page: number
  per_page: number
  keyword?: string
  category?: string
  tags?: string[]
}

/** 报告用例搜索请求体（ReportSearchCasesRequest） */
export interface ReportSearchCasesDto {
  keyword?: string | null
  category?: string | null
  categories?: string[]
  include_untagged?: boolean | null
  tags?: string[]
  metrics?: string[]
  sort_by?: string
  sort_metric?: string | null
  sort_order?: string
  page: number
  per_page: number
}

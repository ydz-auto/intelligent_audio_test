/**
 * 报告域领域模型（domain 层）。
 * 形态对照 api_gateway/schemas/report.py 实测 schema（ReportListItem/ReportListData/
 * ReportSummarySimplified/ReportDetailData/ReportDeviceStat/ReportApiStat/ReportListQuery
 * /ReportSearchCasesRequest），counts 对照 report_query_sevice.get_tab_counts 返回
 * （all/draft/published/comparison 四键）。
 * INT-434 重实施（v2.2）：按 15_报告域.md §1 实测层级补 raw_data / all_metrics 配置数组 /
 * tag_metric_data / case_type_stats / tables / field_mappings / detailed_results /
 * 用例级全量字段（results/referenceParams/algorithmResults/audios）。
 * 接线卡 INT-643：报告域 infra 已切真实接口（reports-api/favoritesApi 经 client.ts），
 * mock 常量（infrastructure/mock/reports-mock.ts）已删除，字段转换只在 infrastructure 层。
 */

export type ReportType = 'task' | 'comparison' | 'secondary_comparison' | 'benchmark'

/** 算法定义（报告展示/工作台「当前算法」卡数据源；GET /algorithm/definitions 子集映射，snake_case 转换见 reports-api） */
export type ReportAlgorithmDefinition = {
  /** 算法类型代码（主键，全局算法 store 存值） */
  type: string
  /** 显示名称 */
  name: string
  groupName?: string | null
  category?: string | null
  description?: string | null
  /** online / offline（卡片「在线/离线」徽章） */
  status?: string
  icon?: string | null
}
export type ReportStatus = 'draft' | 'published'

export type ReportViewMode = 'table' | 'card'
/** 主排序维度（15_报告域.md §2/§2.1：创建时间/报告名称/状态/算法为主，通过率/用例数保留；类型不提供排序） */
export type ReportSortBy =
  | 'created_at'
  | 'name'
  | 'status'
  | 'algorithm'
  | 'pass_rate'
  | 'total_cases'
export type ReportSortOrder = 'asc' | 'desc'
export type ReportTimeRange = 'today' | 'yesterday' | 'week' | 'month' | 'custom'

export interface ReportListItemSummary {
  total_cases: number
  completed_cases: number
  failed_cases: number
  pass_rate: number
  /** 对比报告：对比任务数 */
  task_count?: number
}

/** GET /reports 列表项（report.py ReportListItem） */export interface ReportListItem {
  id: number
  name: string
  type: ReportType
  task_id?: number
  task_name: string
  algorithm_type?: string
  /** 任务类型（e2e/api/mixed；报告中心筛选 §2 实测 :186） */
  task_type?: string
  /** 设备类型（smart_speaker/car_voice/headphone；报告中心筛选 §2 实测 :187） */
  device_type?: string
  /** 创建者（报告中心筛选 §2 实测 :188） */
  creator?: string
  summary: ReportListItemSummary
  description?: string
  status: ReportStatus
  created_at: string
  updated_at?: string
  /** INT-141：收藏标记 / 回收站字段（INT-219 口径） */
  is_favorite?: boolean
  deleted?: boolean
  deleted_at?: string
  deleted_by_user_id?: number
}

/** GET /reports 响应（report.py ReportListData） */
export interface ReportListData {
  items: ReportListItem[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** GET /reports/counts（report_query_sevice.get_tab_counts 返回；口径修正 2026-10-16 取消页签，改为单一列表全量分类计数） */
export interface ReportCounts {
  all: number
  draft: number
  published: number
  comparison: number
  /** Benchmark 报告计数（P3-：徽章行 4 枚固定，Benchmark 分项供类型 chips/后续消费） */
  benchmark?: number
}

/** GET /reports 查询（report.py ReportListQuery；favorite/deleted 直传） */
export interface ReportListQuery {
  page: number
  per_page?: number
  report_type?: string
  status?: string
  task_id?: number
  keyword?: string
  /** 高级搜索：任务类型（e2e/api/mixed，§2 :186） */
  task_type?: string
  /** 高级搜索：设备类型（§2 :187） */
  device_type?: string
  /** 高级搜索：创建者（§2 :188） */
  creator?: string
  start_time?: string
  end_time?: string
  algorithm_type?: string
  sort_by: string
  order: string
  favorite: boolean
  deleted: boolean
}

export interface ReportMetricValue {
  id?: number
  metric: string
  value: number
  /** 五档评分（0-5；块一「得分」真实字段，缺省时显示「—」） */
  score?: number
  /** 详情·错误（块一可折叠长文本；>50 字展开/收起） */
  error?: string
}

/** report.py ReportDeviceStat */
export interface ReportDeviceStat {
  id: number
  name: string
  model?: string
  type?: string
  system?: string
  system_version?: string
  status?: string
  metrics?: Record<string, unknown>
  total_cases: number
  completed_cases: number
  failed_cases: number
  success_rate: number
}

/** report.py ReportApiStat */
export interface ReportApiStat {
  id: number
  name: string
  status?: string
  max_process?: number
  health_score?: number
  metrics?: Record<string, unknown>
  total_cases: number
  completed_cases: number
  failed_cases: number
  success_rate: number
  avg_response_time?: number
  stability?: number
}

/** report.py ReportDeviceInfo（报告快照设备信息） */
export interface ReportDeviceInfo {
  id: number
  name: string
  model?: string
  description?: string
  type?: string
  system?: string
  system_version?: string
  status?: string
  last_online_at?: string
}

/** report.py ReportApiInfo（报告快照 API 信息） */
export interface ReportApiInfo {
  id: number
  name: string
  vendor?: string
  api_url?: string
  description?: string
  status?: string
  max_process?: number
  health_score?: number
}

/** report.py ReportResourceHeader */
export interface ReportResourceHeader {
  key: string
  label: string
  type?: string
  id?: number
  name?: string
  version?: string
  editable?: boolean
  /** 结果类型（V9.7.10 资源名 result_type 后缀：realtime/final/…；resource label 展示） */
  result_type?: string
}

/** metric_data 扁平格式（§1.2：[{resource, metrics:[{id,metric,value}]}]，双格式兼容） */
export interface ReportMetricDataGroup {
  resource: string
  metrics?: ReportMetricValue[]
  /** §1.2 flatten_metric_data 双格式之一：[{resource, categories:[{categoryId, categoryName, metrics}]}] */
  categories?: {
    categoryId?: string
    categoryName: string
    metrics: ReportMetricValue[]
  }[]
}

/** §1.2 raw_data 资源级原始值集合（flatten_raw_data 归一） */
export interface ReportRawDataGroup {
  resource: string
  metrics: { metric: string; values: number[] }[]
}

/** §1.2 all_metrics 指标配置（normalize.py 按 raw_data 过滤 + 补回主维度） */
export interface ReportMetricConfig {
  id?: number | string
  name: string
  unit?: string
  decimal_places?: number
  statistic_method?: string
  dimension_type?: 'main' | 'sub'
  parent_dimension_id?: number | string
  parent_dimension_name?: string
}

/** §1.2 all_case_tags 标签（负责人新加：标签含分类） */
export interface ReportTag {
  id?: string
  tag_id?: string
  tag_name: string
  category_id?: string
  category_name?: string
}

/** §1.2 case_categories 用例分组 */
export interface ReportCaseCategory {
  id?: string
  category_id?: string
  category_name: string
  metrics?: ReportMetricValue[]
}

/** §1.2 tag_metric_data（flatten_tag_metric_data） */
export interface ReportTagMetricGroup {
  resource: string
  tags: {
    tag_id?: string
    tag_name: string
    category_id?: string
    category_name?: string
    metrics: ReportMetricValue[]
  }[]
}

/** §1.2 case_type_stats（flatten_case_type_stats） */
export interface ReportCaseTypeStatGroup {
  group_id: number | string
  group_name: string
  metrics: ReportMetricValue[]
}

/** §1.2 tables（报告生成时预烘焙的对比表格） */
export interface ReportComparisonTable {
  title: string
  columns: ReportComparisonColumn[]
  data: Record<string, unknown>[]
  default_collapsed?: boolean
}

export interface ReportComparisonColumn {
  key: string
  label: string
  type?: 'status' | 'percentage' | 'number' | 'text' | 'icon'
}

/** §4.6 对比配置（对比维度 × 对比指标 × 对比方式；INT-596 P3 补全「对比配置」页签） */
export interface ReportCompareConfig {
  /** 对比维度：test_cases / metrics / devices / execution_time */
  dimension: string
  /** 对比指标多选 */
  metrics: string[]
  /** 对比方式：horizontal / vertical */
  mode: string
}

/** §1.2 field_mappings（用例卡片字段映射） */
export interface ReportFieldMappings {
  algorithmType: { result: string[]; reference: string[] }
}

/** §1.2/§1.3 用例音频 */
export interface ReportAudioItem {
  audio_id: number | string
  audio_name?: string
  audio_type?: string
  spl?: number
  play_order?: number
  noise_spl?: number
  device_name?: string
  /** 结果音频 url（外链） */
  url?: string
}

/** §1.3 用例执行结果行 */
export interface ReportCaseResult {
  resource: string
  status?: string
  /** 结果类型（V9.7.10 资源名 result_type 后缀：realtime/final/…；设备/API 执行结果行徽标） */
  result_type?: string
  startTime?: string
  endTime?: string
}

/** §1.3 算法结果扁平项（_expand_rounds 展开 @round:N） */
export interface ReportAlgorithmResult {
  paramCode: string
  paramType?: string
  label?: string
  roundNumber?: number
  dimensionName?: string
  device?: string
  value?: unknown
  /** 多轮结构（voice_llm 保留 rounds 为 json） */
  rounds?: unknown
}

/** §1.3 用例参考参数 */
export interface ReportReferenceParam {
  code: string
  type?: string
  /** 展示 label（参考/用例参数 kv 表 key；缺省回退 code） */
  label?: string
  value?: unknown
  segments?: unknown
  text?: string
  json?: unknown
}

/** GET /reports/{id} summary 子集（report.py ReportSummarySimplified 全字段，INT-439 v2.2） */
export interface ReportSummary {
  total_cases: number
  completed_cases: number
  failed_cases: number
  resources: string[]
  resource_headers: ReportResourceHeader[]
  raw_data: ReportRawDataGroup[]
  metric_data: ReportMetricDataGroup[]
  tag_metric_data: ReportTagMetricGroup[]
  case_categories: ReportCaseCategory[]
  all_case_tags: ReportTag[]
  all_tags?: ReportTag[]
  all_metrics: ReportMetricConfig[]
  case_type_stats: ReportCaseTypeStatGroup[]
  device_stats: ReportDeviceStat[]
  api_stats: ReportApiStat[]
  devices: ReportDeviceInfo[]
  apis: ReportApiInfo[]
  tables?: ReportComparisonTable[]
  field_mappings?: ReportFieldMappings[]
  /** 用例聚合（SpecificCase/Tag/Category 回退重算源） */
  cases?: ReportCaseItem[]
  detailed_results?: unknown[]
  /** 对比报告：对比任务数（§3.2 报告头「{taskCount} 个任务对比」真实字段） */
  task_count?: number
}

/** GET /reports/{id}（report.py ReportDetailData） */
export interface ReportDetailData {
  id: number
  name: string
  type: ReportType
  task_id?: number
  task_type?: string
  task_name: string
  algorithm_type?: string
  summary: ReportSummary
  description?: string
  status: ReportStatus
  analysis?: string
  created_at: string
  updated_at?: string
  deleted?: boolean
  deleted_at?: string
  deleted_by_user_id?: number
}

/** GET /reports/{id}/progress 报告生成进度（report_handlers.handle_get_report_progress 实测契约） */
export interface ReportProgress {
  report_id: number
  task_id: number | null
  /** generating（生成锁持有）→ completed（报告行落库即完成）；failed 由 SSE 失败事件表达 */
  status: string
  /** 0-100（generating 时按任务完成用例数推导） */
  progress: number
  /** 报告落库后状态（draft/published） */
  report_status?: string
}

/** 具体用例（POST /reports/{id}/cases/search 返回项；build_case_item 全字段，§1.3） */
export interface ReportCaseItem {
  id: string
  name: string
  description?: string
  category?: string
  tags: string[]
  /** {resource:{dimension:value}} 或 [{resource, metrics}] 双格式（按算法类型区分） */
  metrics: ReportCaseMetrics
  /** 用例参数（算法输入参数，按轮次展示；§3.5.4 caseParams 契约） */
  caseParams?: Record<string, ReportReferenceParam>
  /** 块一「得分」真实字段（dict 格式 metrics 的评分兜底；数组格式走 ReportMetricValue.score） */
  metricScore?: Record<string, number>
  /** 块一「详情·错误」真实字段（dict 格式 metrics 的错误文本兜底；数组格式走 ReportMetricValue.error） */
  metricError?: Record<string, string>
  results: ReportCaseResult[]
  audios: ReportAudioItem[]
  referenceParams?: Record<string, ReportReferenceParam>
  algorithmResults?: ReportAlgorithmResult[]
  algorithmType?: string
  logs?: string
  /** 展示态覆盖字段（详情 Dialog 消费） */
  overall_status?: 'pass' | 'fail' | 'warning' | 'skip' | 'unknown'
}

/** 用例 metrics 双格式 */
export type ReportCaseMetrics =
  | Record<string, Record<string, number>>
  | ReportMetricDataGroup[]

/** 用例搜索分页响应 */
export interface ReportCaseListData {
  items: ReportCaseItem[]
  total: number
  page: number
  per_page: number
  pages: number
}

/**
 * 用例日志文件（GET /reports/{id}/cases/{caseId}/logs 项；15_报告域.md §4.10a，INT-1067）。
 * name 与下载 ZIP arcname / ?files= 匹配值同一套逻辑名（INT-1062 命名一致性）。
 */
export interface ReportLogFile {
  /** 文件名（= 下载 ZIP arcname = files= 匹配值） */
  name: string
  /** 文件大小（bytes） */
  size: number
  /** 修改时间（RFC3339；business 日志无 mtime 时后端省略该字段） */
  updatedAt?: string
}

/** POST /reports/{id}/cases/search（report.py ReportSearchCasesRequest 全参） */
export interface ReportSearchCasesRequest {
  keyword?: string
  category?: string
  categories?: string[]
  include_untagged?: boolean
  tags?: string[]
  metrics?: string[]
  sort_by?: 'name' | 'category' | 'createdat' | 'metric'
  sort_metric?: string
  sort_resource?: string
  sort_order?: 'asc' | 'desc'
  page: number
  per_page: number
}

/** 分组/标签对比矩阵（§3.3.5/3.3.6：{分组:{资源:{指标:number|number[]}}}） */
export type MetricMatrix = Record<
  string,
  Record<string, Record<string, number | number[]>>
>

/** PUT /reports/{id} 摘要字段白名单（ReportUpdateSummaryField 在册） */
export interface ReportSummaryUpdate {
  caseCategories?: ReportCaseCategory[]
  allCaseTags?: ReportTag[]
  allTags?: ReportTag[]
  resourceHeaders?: ReportResourceHeader[]
}

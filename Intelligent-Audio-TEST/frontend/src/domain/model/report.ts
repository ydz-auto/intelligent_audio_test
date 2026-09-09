/**
 * Report 领域模型 —— camelCase
 *
 * 真实后端契约（已校准）：
 * - 列表：GET /reports → ReportListData{items,total,page,per_page,pages}
 *   ReportListItem = {id, name, type, task_id, task_name, algorithm_type,
 *   summary{total_cases,completed_cases,failed_cases,pass_rate,task_count}, description, status, created_at, updated_at}
 *   （api_gateway/schemas/report.py::ReportListItem）
 * - 详情：GET /reports/{id} → report_service 聚合根 _aggregate_to_dict：
 *   {id, task_id, report_type, status, config, created_at, summaries[], cases[], metric_stats[], raw_data[]}
 *   （report_service/interfaces/grpc/servicers.py::_aggregate_to_dict）
 * - report_type 是报告类型后端原值（task/comparison/secondary_comparison/standard），
 *   Enum 值不转换，只转字段名。
 */
import { ReportStatus } from '@/domain/enums'

/** 报告类型（后端原值；reports 表 type 列：task/comparison/secondary_comparison/standard） */
export type ReportType = 'task' | 'comparison' | 'secondary_comparison' | 'standard'

/** 报告状态（后端原值） */
export type ReportState = typeof ReportStatus[keyof typeof ReportStatus] | (string & {})

/** 报告列表项摘要统计（ReportListItemSummary → camelCase） */
export interface ReportListItemSummary {
  totalCases: number
  completedCases: number
  failedCases: number
  passRate: number
  taskCount?: number
}

/** 报告列表项（ReportListItem → camelCase） */
export interface ReportListItemDomain {
  id: number
  name: string
  type: string
  taskId?: number
  taskName: string
  algorithmType?: string
  summary: ReportListItemSummary
  description?: string
  status: ReportState
  createdAt: string
  updatedAt?: string
}

/** 报告列表响应（ReportListData → camelCase） */
export interface ReportListData {
  items: ReportListItemDomain[]
  total: number
  page: number
  perPage: number
  pages: number
}

// ===== 详情侧（聚合根 + summary 预留形状） =====

/** 报告指标配置（summary.all_metrics 元素） */
export interface ReportMetricConfig {
  id?: string | number
  name: string
  unit?: string
  decimalPlaces?: number
  /** 统计方式（average / weighted_wer / pass_rate 等，对齐报告聚合策略） */
  statisticMethod?: string
  /** 维度类型：main 主维度 / sub 子维度（子维度归入父维度组显示） */
  dimensionType?: 'main' | 'sub' | string
  parentDimensionId?: number | string | null
  parentDimensionName?: string | null
}

export interface ReportMetricValue {
  id?: number | null
  metric: string
  value: number
}

export interface ReportMetricValues {
  metric: string
  values: number[]
}

/** 原始数据分组（flatten_raw_data 输出） */
export interface ReportRawDataGroup {
  resource: string
  metrics: ReportMetricValues[]
}

export interface ReportMetricCategoryGroup {
  categoryId: string
  categoryName: string
  metrics: ReportMetricValue[]
}

export interface ReportMetricByResource {
  resource: string
  categories: ReportMetricCategoryGroup[]
  /** 扁平行（resource 级别全局平均，无分类维度） */
  metrics?: ReportMetricValue[]
}

export interface ReportTagMetricTagGroup {
  tagId: string
  tagName: string
  categoryId?: number | null
  categoryName?: string | null
  metrics: ReportMetricValue[]
}

export interface ReportTagMetricByResource {
  resource: string
  tags: ReportTagMetricTagGroup[]
}

export interface ReportCaseTypeStatRow {
  groupId: string
  groupName: string
  metrics: ReportMetricValue[]
}

/** 报告详情关联设备统计（ReportDeviceStat → camelCase） */
export interface ReportDeviceStat {
  id: number
  name: string
  model?: string
  type?: string
  system?: string
  systemVersion?: string
  status?: string
  metrics?: Record<string, number> | null
  totalCases: number
  completedCases: number
  failedCases: number
  successRate: number
}

/** 报告详情关联 API 统计（ReportApiStat → camelCase） */
export interface ReportApiStat {
  id: number
  name: string
  status?: string
  maxProcess?: number | null
  healthScore?: number | null
  metrics?: Record<string, number> | null
  totalCases: number
  completedCases: number
  failedCases: number
  successRate: number
  avgResponseTime?: number | null
  stability?: number | null
}

/** 报告详情关联设备信息（ReportDeviceInfo → camelCase） */
export interface ReportDeviceInfo {
  id: number
  name: string
  model?: string
  description?: string
  type?: string
  system?: string
  systemVersion?: string
  appName?: string
  appVersion?: string
  location?: string
  maxAudioDuration?: number | null
  needsPromptAudio?: boolean | null
  connectionType?: string
  keywords?: string
  serialNumber?: string
  ip?: string
  status?: string
  lastOnlineAt?: string | null
  createdAt?: string | null
  updatedAt?: string | null
}

/** 报告详情关联 API 信息（ReportApiInfo → camelCase） */
export interface ReportApiInfo {
  id: number
  name: string
  vendor?: string
  apiUrl?: string
  description?: string
  status?: string
  maxProcess?: number | null
  maxTimeout?: number | null
  maxAudioDuration?: number | null
  healthScore?: number | null
  createdAt?: string | null
  updatedAt?: string | null
}

/** 资源表头（ReportResourceHeader → camelCase） */
export interface ReportResourceHeader {
  key: string
  label: string
  type?: string
  id?: number | null
  name?: string | null
  version?: string | null
  editable?: boolean | null
}

/** 报告详情摘要（summary 预留形状，camelCase；对应 ReportUpdateSummaryField 可写字段） */
export interface ReportSummary {
  totalCases?: number
  completedCases?: number
  failedCases?: number
  passRate?: number
  passedCases?: number
  avgScore?: number
  /** 对比报告涉及的任务数（对应后端 summary.task_count） */
  taskCount?: number
  allMetrics?: ReportMetricConfig[]
  detailedResults?: DetailedResult[]
  deviceStats?: ReportDeviceStat[]
  apiStats?: ReportApiStat[]
  /** 分类×资源×指标均值矩阵（后端原 key 为分类名/资源键，非字段名，保留 Record） */
  metrics?: Record<string, number>
  rawData?: ReportRawDataGroup[]
  metricData?: ReportMetricByResource[]
  tagMetricData?: ReportTagMetricByResource[]
  caseTypeStats?: ReportCaseTypeStatRow[]
  overallSuccessRate?: number
  stability?: number
  /** 维度名 → 值（后端原 key 为维度名，非字段名，保留 Record） */
  dimensionValues?: Record<string, number>
  devices?: Array<string | ReportDeviceInfo>
  apis?: Array<string | ReportApiInfo>
  resourceHeaders?: ReportResourceHeader[]
  caseCategories?: string[]
  allCaseTags?: string[]
  /** 兼容旧字段（与 allCaseTags 并存，后端遗留） */
  allTags?: string[]
  resources?: string[]
  fieldMappings?: Record<string, ReportFieldMapping>
  cases?: ReportCaseEntityDomain[]
}

/** 报告详情用例子实体（_aggregate_to_dict cases[] → camelCase） */
export interface ReportCaseEntityDomain {
  id: number
  reportId: number
  testCaseId: string
  /** 用例结果汇总（后端 result_summary 内键为数据 key 非字段名，保留 Record） */
  resultSummary: Record<string, unknown>
  score?: number | null
}

/** 报告详情指标统计子实体（_aggregate_to_dict metric_stats[] → camelCase） */
export interface ReportMetricStatsDomain {
  id: number
  reportId: number
  metricName: string
  avg: number
  min: number
  max: number
  stdDev: number
  sampleCount: number
}

/** 报告详情原始数据子实体（_aggregate_to_dict raw_data[] → camelCase） */
export interface ReportRawDataEntityDomain {
  id: number
  reportId: number
  dataType: string
  data: Record<string, unknown>
}

/** 报告算法结果项（algorithm_results[] 元素 → camelCase） */
export interface ReportAlgorithmResultItem {
  paramCode: string
  paramType: string
  roundNumber?: number
  dimensionName?: string | null
  label?: string
  device?: string
  /**
   * 结果值载荷（数据驱动结构，原样保留）：
   * 多轮结构为 { rounds, aggregated, total_rounds }（aggregated/output 内键为指标名等数据 key，
   * 由 utils/reportMultiRound 专用解析器消费）；时间轴类型（rttm/stm）为分段数组或 JSON 字符串。
   */
  value?: string | number | boolean | Record<string, unknown> | unknown[]
}

/** 报告参考参数条目（reference_params 字典值 → camelCase；字典键为参数 code 数据 key，保留原样） */
export interface ReportReferenceParamEntry {
  code?: string
  type?: string
  /** 参数原始值载荷（rttm/stm 时为 dict，由 adapter 原样保留） */
  value?: unknown
  label?: string
  roundNumber?: number
  /** rttm/stm 参数：分段数据 */
  segments?: unknown[]
  /** rttm/stm 参数：文本说明 */
  text?: string
  /** rttm/stm 参数：json 字符串 */
  json?: string
  annotationCode?: string
  annotationFormat?: string
}

/** 算法字段映射项（field_mapping result/reference 数组元素 → camelCase） */
export interface ReportFieldMappingItem {
  paramCode?: string
  paramType?: string
  label?: string
  roundNumber?: number | null
  dimensionName?: string | null
  value?: string
  device?: string
}

/** 算法字段映射快照（{result, reference} 数组 → camelCase） */
export interface ReportFieldMapping {
  result?: ReportFieldMappingItem[]
  reference?: ReportFieldMappingItem[]
}

/** 用例维度明细（detailed_results 元素预留形状；后端键名历史遗留混用，宽松可选） */
export interface DetailedResult {
  id: string | number
  caseName?: string
  score?: number
  result?: string
  executionStatus?: string
  testCaseId?: string | number
  testCaseName?: string
  deviceName?: string
  apiName?: string
  audioName?: string
  createdAt?: string
  errorMessage?: string
  /** 用例分组（后端 test_case_group） */
  testCaseGroup?: { id: unknown; name: string }
  /** 用例标签列表（后端 test_case_tags） */
  testCaseTags?: Array<string | { name?: string }>
  /** 嵌套用例对象（后端 test_case，含 tags 等） */
  testCase?: { tags?: Array<string | { name?: string }> }
  /** 设备信息 */
  device?: { id: unknown; name: string }
  /** API 信息 */
  api?: { id: unknown; name: string }
  /** ASR 结果块 */
  asr?: { referenceText?: string; resultText?: string }
  /** 翻译结果块 */
  translation?: { referenceText?: string; resultText?: string }
  /** 维度评分列表（后端 dimension_scores） */
  dimensionScores?: Array<{ dimensionName: string; score: number }>
  /** 动态指标键值对（键为指标名，保留 Record） */
  metrics?: Record<string, unknown>
  /** 音频列表 */
  audios?: unknown[]
  /** 用例描述 */
  description?: string
  /** 日志 */
  logs?: string
  /** 用例类型（后端 test_case_type） */
  testCaseType?: string
  /** 音频文件路径 */
  audioFilePath?: string
  /** 音频时长 */
  audioDuration?: number
  /** 音频ID */
  audioId?: string | number
}

/** 报告详情（聚合根形状；name/taskName/title 等为兼容展示字段，来源 config JSON） */
export interface Report {
  id: string | number
  /** 报告名称（列表来自 name 列；详情来自 config.name，缺失回退 title/空串） */
  name: string
  /** 报告类型后端原值 */
  type: ReportType | (string & {})
  status: ReportState
  createdAt: string
  updatedAt?: string
  taskId?: string | number
  /** 任务名称（仅列表/对比报告聚合输出；详情聚合根无此字段） */
  taskName?: string
  algorithmType?: string
  description?: string
  summary?: ReportSummary
  detailedResults?: DetailedResult[]
  conclusion?: string
  /** 报告编辑标题（ReportUpdateRequest.title） */
  title?: string
  /** 聚合根 config JSON（_aggregate_to_dict 输出，键为数据 key 非字段名） */
  config?: Record<string, unknown>
  /** 详情聚合根 summaries[]（摘要元数据行） */
  summaries?: Array<{
    id: number
    reportId: number
    metricName: string
    metricValue: number
    metadata: Record<string, unknown>
  }>
  /** 详情聚合根 cases[] */
  cases?: ReportCaseEntityDomain[]
  /** 详情聚合根 metric_stats[] */
  metricStats?: ReportMetricStatsDomain[]
  /** 详情聚合根 raw_data[] */
  rawData?: ReportRawDataEntityDomain[]
}

/** 报告对比结果（compare/secondary-compare 响应） */
export interface CompareResult {
  /** 生成的报告 ID（compare） */
  reportId?: string | number
  /** 兼容旧响应字段 */
  id?: string | number
  /** 二次对比返回的 key 列表 */
  reportKey?: Array<string | number>
  /** 生成状态（exists/generating/completed） */
  status?: string
  /** 差异描述（预留） */
  differences?: unknown[]
}

/** 报告列表查询参数（Domain camelCase；adapter 负责转 ReportListQuery snake_case） */
export interface ReportListQuery {
  page: number
  perPage: number
  /** 排序字段（发往后端保持后端原值，如 created_at） */
  sortBy: string
  order: 'asc' | 'desc'
  /** 报告类型过滤（后端 query 别名 type → report_type） */
  type?: string
  status?: string
  keyword?: string
  startTime?: string
  endTime?: string
  algorithmType?: string
}

// ===== 对比报告展示模型 =====

/** 对比面板中可选的设备/API 资源 */
export interface ComparisonDevice {
  id: string | number
  name: string
  type: '设备' | 'API'
  selected: boolean
  version?: string
}

/** 资源指标对比行数据 */
export interface DeviceAPIComparisonItem {
  id: string | number
  name: string
  type: '设备' | 'API'
  version: string
  status: string
  totalCases: number
  successRate: number
  avgResponseTime: number
  stability: number
}

/** 用例执行统计行数据 */
export interface CaseExecutionItem {
  id: string | number
  name: string
  total: number
  executed: number
  completed: number
  failed: number
  successRate: number
  failedRate: number
}

// ===== 对比组件内存结构 =====

/** 指标累加器（对比组件专用） */
export interface MetricAccumulator {
  sum: number
  count: number
  values: number[]
}

/** 指标矩阵（对比组件专用） */
export type MetricMatrix = Record<string, Record<string, Record<string, number | number[]>>>

/** 对比表格列定义 */
export interface ComparisonColumn {
  key: string
  label: string
  editable: boolean
  resize: boolean
  class: string
  color?: string
  unit?: string
}

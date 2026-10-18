/**
 * reports 域 API（infrastructure 层；接线卡 INT-643）。
 * 全部请求经 client.ts 统一 fetch 封装（baseURL / JWT / 错误码 / SSE 通道），端点对照
 * api_gateway 实测契约：
 *   GET  /reports                        （report_bp.py:29，ReportListQuery 全参，服务端分页）
 *   GET  /reports/tab-counts             （report_bp.py:34，{all,draft,published,comparison}）
 *   GET  /reports/{id}                   （report_bp.py:51，ReportDetailData）
 *   POST /reports/{id}/cases/search      （report_bp.py:116，ReportSearchCasesRequest）
 *   GET  /reports/{id}/cases/{caseId}/logs/download
 * 变更类：
 *   PUT /reports/{id}                    （ReportUpdateRequest）
 *   POST /reports/{id}/publish、POST /reports/{id}/regenerate
 *   DELETE /reports/{id}、POST /reports/batch-delete
 *   POST /reports/generate-task、POST /reports/compare、POST /reports/secondary-compare
 *   POST /reports/export（binary）
 * 收藏/回收站（favorite_trash_bp.py:110-137，INT-215 口径）：
 *   POST/DELETE /reports/{report_id}/favorite、POST /reports/{report_id}/restore、
 *   DELETE /reports/{report_id}/purge。
 * 已知后端缺口（本卡评论留证据）：POST /benchmarks/reports 不存在（publishBenchmarkReport
 * 保持桩）；report-studio 端点不存在（reportStudioApi.ts 桩，FEAT 卡已开）。
 */
import type {
  ReportAlgorithmDefinition,
  ReportCaseCategory,
  ReportCaseItem,
  ReportCaseListData,
  ReportCompareConfig,
  ReportCounts,
  ReportDetailData,
  ReportListData,
  ReportListQuery,
  ReportMetricValue,
  ReportSearchCasesRequest,
  ReportSummary,
  ReportSummaryUpdate,
  ReportTag,
} from '@/domain/models/report'
import type {
  ReportCaseAverageMetric,
  ReportCaseAverageMetricGroup,
  ReportCaseAveragesData,
} from '@/domain/models/report-statistics'

import { request } from './client'

/** 生成报告/对比 Dialog 任务选择器数据源（GET /tasks 已完成子集映射） */
export interface CompletedTaskOption {
  id: number
  name: string
  type: string
  status: string
  completed_at: string
}

// ---------------------------------------------------------------------------
// 查询类
// ---------------------------------------------------------------------------

/** GET /reports 列表（ReportListQuery 全参透传，服务端分页/排序/筛选） */
export async function fetchReportList(
  query: ReportListQuery
): Promise<ReportListData> {
  const params: Record<string, unknown> = { ...query }
  return request<ReportListData>('GET', '/reports', undefined, { params })
}

/** GET /reports/tab-counts 全量分类计数（all/draft/published/comparison 四键服务端聚合） */
export async function fetchReportCounts(): Promise<ReportCounts> {
  return request<ReportCounts>('GET', '/reports/tab-counts')
}

/**
 * GET /algorithm/definitions（algorithm:read；报告展示/工作台「当前算法」卡数据源）。
 * 响应 { items: [AlgorithmDetailResponse] } → 域模型子集（ReportAlgorithmDefinition）。
 * 契约对位 api_gateway/schemas/_algorithm_definition_schemas.py AlgorithmDetailResponse。
 */
export async function fetchAlgorithmDefinitions(): Promise<ReportAlgorithmDefinition[]> {
  const raw = await request<unknown>('GET', '/algorithm/definitions')
  const items = Array.isArray(raw)
    ? raw
    : Array.isArray((raw as { items?: unknown[] } | null)?.items)
      ? (raw as { items: unknown[] }).items
      : []
  return (items as Record<string, unknown>[]).map((item) => ({
    type: str(item.type) ?? '',
    name: str(item.name) ?? '',
    groupName: item.group_name !== undefined ? str(item.group_name) : undefined,
    category: item.category !== undefined ? str(item.category) : undefined,
    description: item.description !== undefined ? str(item.description) : undefined,
    status: item.status !== undefined ? str(item.status) : undefined,
    icon: item.icon !== undefined ? str(item.icon) : undefined,
  }))
}

/** GET /tasks 已完成子集（生成/对比 Dialog 任务选择器数据源；status=completed 服务端过滤） */
export async function fetchCompletedTasks(): Promise<CompletedTaskOption[]> {
  const data = await request<{ items: TaskOptionRaw[] }>('GET', '/tasks', undefined, {
    params: { status: 'completed', per_page: 100, deleted: false },
  })
  return (data.items ?? []).map((item) => ({
    id: item.id,
    name: item.name,
    type: typeof item.config?.task_type === 'string' ? item.config.task_type : 'e2e',
    status: item.status,
    completed_at: item.completed_at ?? item.updated_at ?? '',
  }))
}

interface TaskOptionRaw {
  id: number
  name: string
  status: string
  completed_at?: string
  updated_at?: string
  config?: { task_type?: string }
}

/** Hero 类型 chips / 收藏计数（全量非回收站项；按 type 客户端聚合，供类型筛选 chips 消费） */
export async function fetchReportTypeCounts(): Promise<{
  typeCounts: Record<string, number>
  favoriteCount: number
}> {
  const data = await fetchReportList({
    page: 1,
    per_page: 1000,
    sort_by: 'created_at',
    order: 'desc',
    favorite: false,
    deleted: false,
  })
  const items = data.items
  const count = (type: string) => items.filter((i) => i.type === type).length
  return {
    typeCounts: {
      all: items.length,
      task: count('task'),
      comparison: count('comparison'),
      secondary_comparison: count('secondary_comparison'),
      benchmark: count('benchmark'),
    },
    favoriteCount: items.filter((i) => i.is_favorite).length,
  }
}

/** GET /reports/{id} 报告详情（404/非法 id → 页面按 ApiError.httpStatus=404 分叉「报告不存在」） */
export async function fetchReportDetail(
  reportId: number
): Promise<ReportDetailData> {
  const raw = await request<unknown>('GET', `/reports/${reportId}`)
  return toReportDetailData(raw)
}

/**
 * Benchmark 报告列表（INT-500 v2.9：列表并入报告中心类型筛选，report_type='benchmark'
 * 统一走 /reports 列表；后端无独立 /benchmarks/reports 端点）。
 */
export async function fetchBenchmarkReports(): Promise<ReportListData> {
  return fetchReportList({
    page: 1,
    per_page: 100,
    report_type: 'benchmark',
    sort_by: 'created_at',
    order: 'desc',
    favorite: false,
    deleted: false,
  })
}

/**
 * 发布 Benchmark 报告（§3.8；排行区块「发布 Benchmark 报告」）。
 * 后端缺口：POST /api/v1/benchmarks/reports 不存在（benchmark_bp.py 无此路由），
 * 保持桩并返回演示态 reportId；待主项目后端立项后替换（证据见本卡交付评论）。
 */
export async function publishBenchmarkReport(): Promise<{ reportId: number }> {
  return { reportId: 1185 }
}

// ---------------------------------------------------------------------------
// 用例搜索 / 日志下载
// ---------------------------------------------------------------------------

/** POST /reports/{id}/cases/search（ReportSearchCasesRequest 全参；响应 snake_case → 域模型） */
export async function searchReportCases(
  reportId: number,
  query: ReportSearchCasesRequest
): Promise<ReportCaseListData> {
  const dto = await request<{
    items?: unknown[]
    total?: number
    page?: number
    per_page?: number
    pages?: number
  }>('POST', `/reports/${reportId}/cases/search`, query)
  const rawItems = Array.isArray(dto.items) ? dto.items : []
  const total = typeof dto.total === 'number' ? dto.total : rawItems.length
  const perPage = typeof dto.per_page === 'number' ? dto.per_page : (query.per_page || 20)
  return {
    items: rawItems.map(toReportCaseItem),
    total,
    page: typeof dto.page === 'number' ? dto.page : query.page,
    per_page: perPage,
    pages: typeof dto.pages === 'number' ? dto.pages : Math.max(1, Math.ceil(total / perPage)),
  }
}

/** GET /reports/{id}/cases/{caseId}/logs/download（logs.zip Blob） */
export async function downloadCaseLogs(
  reportId: number,
  caseId: string
): Promise<{ blob: Blob; size: number }> {
  const blob = await request<Blob>(
    'GET',
    `/reports/${reportId}/cases/${caseId}/logs/download`,
    undefined,
    { responseType: 'blob' }
  )
  return { blob, size: blob.size }
}

// ---------------------------------------------------------------------------
// 变更类
// ---------------------------------------------------------------------------

/** PUT /reports/{id} 更新报告（name/description/analysis/summary 白名单；summary 经 snake_case 转换） */
export async function updateReport(
  reportId: number,
  payload: {
    name?: string
    description?: string
    analysis?: string
    summary?: ReportSummaryUpdate & { analysisConclusion?: string; conclusion?: string }
  }
): Promise<{ success: boolean }> {
  await request('PUT', `/reports/${reportId}`, toReportUpdateBody(payload))
  return { success: true }
}

/** 报告更新请求体：summary 顶层白名单 camelCase → snake_case（ReportUpdateSummaryField 契约） */
function toReportUpdateBody(payload: {
  name?: string
  description?: string
  analysis?: string
  summary?: ReportSummaryUpdate & { analysisConclusion?: string; conclusion?: string }
}): Record<string, unknown> {
  const body: Record<string, unknown> = {}
  if (payload.name !== undefined) body.name = payload.name
  if (payload.description !== undefined) body.description = payload.description
  if (payload.analysis !== undefined) body.analysis = payload.analysis
  if (payload.summary !== undefined) {
    const s = payload.summary
    const summary: Record<string, unknown> = { ...s }
    if (s.caseCategories !== undefined) summary.case_categories = s.caseCategories
    if (s.allCaseTags !== undefined) summary.all_case_tags = s.allCaseTags
    if (s.allTags !== undefined) summary.all_tags = s.allTags
    if (s.resourceHeaders !== undefined) summary.resource_headers = s.resourceHeaders
    for (const key of ['caseCategories', 'allCaseTags', 'allTags', 'resourceHeaders']) {
      delete summary[key]
    }
    body.summary = summary
  }
  return body
}

/** POST /reports/{id}/publish */
export async function publishReport(reportId: number): Promise<{ success: boolean }> {
  await request('POST', `/reports/${reportId}/publish`)
  return { success: true }
}

/** DELETE /reports/{id}（软删） */
export async function deleteReport(reportId: number): Promise<{ success: boolean }> {
  await request('DELETE', `/reports/${reportId}`)
  return { success: true }
}

/** POST /reports/batch-delete（批量软删；hard_delete 语义由后端按 body 判定） */
export async function batchDeleteReports(ids: number[]): Promise<{ success: boolean }> {
  await request('POST', '/reports/batch-delete', { ids })
  return { success: true }
}

/** POST /reports/{id}/regenerate（仅任务报告） */
export async function regenerateReport(reportId: number): Promise<{ success: boolean }> {
  await request('POST', `/reports/${reportId}/regenerate`)
  return { success: true }
}

/** POST /reports/generate-task（GenerateTaskReportRequest） */
export async function generateTaskReport(payload: {
  task_id: number
  name?: string
  description?: string
}): Promise<{ report_id: number }> {
  return request<{ report_id: number }>('POST', '/reports/generate-task', payload)
}

/** POST /reports/compare（CompareReportsRequest；§4.6 对比配置后端未立项，不随批发送） */
export async function compareReports(payload: {
  task_ids: number[]
  name?: string
  description?: string
  config?: ReportCompareConfig
}): Promise<{ report_id: number }> {
  return request<{ report_id: number }>('POST', '/reports/compare', {
    task_ids: payload.task_ids,
    name: payload.name,
    description: payload.description,
  })
}

/** POST /reports/secondary-compare（SecondaryCompareRequest；config 同 compare 不入参） */
export async function secondaryCompareReports(payload: {
  report_ids: number[]
  description?: string
  config?: ReportCompareConfig
}): Promise<{ report_id: number }> {
  return request<{ report_id: number }>('POST', '/reports/secondary-compare', {
    report_ids: payload.report_ids,
    description: payload.description,
  })
}

/** POST /reports/case-averages（GetCaseAveragesRequest；任务用例平均值统计，Vue
 * reportsApi.getCaseAveragesByFilters 同套契约）。统计页「评估维度」/散点·热力图/
 * 评估指标·设备性能卡数据源；响应 snake_case → 域模型（本层唯一转换点）。 */
export async function fetchCaseAverages(
  taskId: number,
  filters?: {
    category?: string
    tags?: string[]
    categories?: string[]
    includeUntagged?: boolean
  }
): Promise<ReportCaseAveragesData> {
  const body: Record<string, unknown> = { task_id: taskId }
  if (filters?.category !== undefined) body.category = filters.category
  if (filters?.tags !== undefined) body.tags = filters.tags
  if (filters?.categories !== undefined) body.categories = filters.categories
  if (filters?.includeUntagged !== undefined) body.include_untagged = filters.includeUntagged
  return toReportCaseAveragesData(await request<unknown>('POST', '/reports/case-averages', body))
}

/** case-averages 响应 snake_case → 域模型（overall_averages/metric_data/resources 逐字段转换） */
function toReportCaseAveragesData(raw: unknown): ReportCaseAveragesData {
  const rec = (raw ?? {}) as Record<string, unknown>
  const toMetric = (m: unknown): ReportCaseAverageMetric => {
    const item = (m ?? {}) as Record<string, unknown>
    return {
      id:
        item.id === undefined || item.id === null
          ? undefined
          : typeof item.id === 'number'
            ? item.id
            : String(item.id),
      metric: str(item.metric ?? item.name ?? '') ?? '',
      value: num(item.value) ?? 0,
    }
  }
  return {
    totalCases: num(rec.total_cases ?? rec.totalCases) ?? 0,
    totalResults: num(rec.total_results ?? rec.totalResults) ?? 0,
    overallAverages: Array.isArray(rec.overall_averages)
      ? (rec.overall_averages as unknown[]).map(toMetric)
      : [],
    metricData: Array.isArray(rec.metric_data)
      ? (rec.metric_data as unknown[]).map((g) => {
          const group = (g ?? {}) as Record<string, unknown>
          const out: ReportCaseAverageMetricGroup = {
            resource: str(group.resource) ?? '',
          }
          if (Array.isArray(group.metrics)) {
            out.metrics = (group.metrics as unknown[]).map(toMetric)
          }
          if (Array.isArray(group.categories)) {
            out.categories = (group.categories as unknown[]).map((c) => {
              const cat = (c ?? {}) as Record<string, unknown>
              return {
                categoryId: (cat.category_id ?? cat.categoryId) as number | string | undefined,
                categoryName: str(cat.category_name ?? cat.categoryName ?? '') ?? '',
                metrics: Array.isArray(cat.metrics) ? (cat.metrics as unknown[]).map(toMetric) : [],
              }
            })
          }
          return out
        })
      : [],
    resources: Array.isArray(rec.resources) ? (rec.resources as unknown[]).map(String) : [],
    resourceHeaders: Array.isArray(rec.resource_headers)
      ? (rec.resource_headers as unknown[]).map(String)
      : undefined,
    rawData: rec.raw_data,
    normalDistribution: rec.normal_distribution,
    filters: rec.filters as ReportCaseAveragesData['filters'],
  }
}

/** POST /reports/export（ReportExportRequest；后端返回二进制文件，调用方触发下载） */
export async function exportReports(payload: {
  ids: number[]
  format: string
}): Promise<Blob> {
  return request<Blob>('POST', '/reports/export', payload, { responseType: 'blob' })
}

/** POST/DELETE /reports/{id}/favorite（favorite=true 收藏、false 取消收藏；幂等） */
export async function toggleReportFavorite(
  reportId: number,
  favorite: boolean
): Promise<{ success: boolean }> {
  await request(favorite ? 'POST' : 'DELETE', `/reports/${reportId}/favorite`)
  return { success: true }
}

/** POST /reports/{id}/restore（回收站恢复） */
export async function restoreReport(reportId: number): Promise<{ success: boolean }> {
  await request('POST', `/reports/${reportId}/restore`)
  return { success: true }
}

/** DELETE /reports/{id}/purge（彻底删除） */
export async function purgeReport(reportId: number): Promise<{ success: boolean }> {
  await request('DELETE', `/reports/${reportId}/purge`)
  return { success: true }
}

// ---------------------------------------------------------------------------
// snake_case → 域模型转换（唯一知道 snake_case 的层；域模型见 domain/models/report.ts）
// ---------------------------------------------------------------------------

function str(value: unknown): string | undefined {
  if (value === undefined || value === null) return undefined
  return String(value)
}

function num(value: unknown): number | undefined {
  if (value === undefined || value === null) return undefined
  const n = Number(value)
  return Number.isFinite(n) ? n : undefined
}

/** 参考/用例参数字典（reference_params/case_params：值对象逐字段转，非对象原样保留键值） */
function toParamDict(raw: unknown): Record<string, import('@/domain/models/report').ReportReferenceParam> | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined
  const out: Record<string, import('@/domain/models/report').ReportReferenceParam> = {}
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      const rec = value as Record<string, unknown>
      out[key] = {
        code: str(rec.code ?? key) ?? key,
        type: rec.type !== undefined ? str(rec.type) : undefined,
        label: rec.label !== undefined ? str(rec.label) : undefined,
        value: rec.value,
        segments: Array.isArray(rec.segments) ? rec.segments : undefined,
        text: rec.text !== undefined ? str(rec.text) : undefined,
        json: rec.json,
      }
    } else {
      out[key] = { code: key, value }
    }
  }
  return out
}

/** 算法结果扁平项（_expand_rounds 展开 @round:N 的 snake_case 字段 → 域模型） */
function toAlgorithmResult(raw: Record<string, unknown>): import('@/domain/models/report').ReportAlgorithmResult {
  return {
    paramCode: str(raw.param_code ?? raw.paramCode ?? '') ?? '',
    paramType:
      raw.param_type !== undefined ? str(raw.param_type) : raw.paramType !== undefined ? str(raw.paramType) : undefined,
    roundNumber: num(raw.round_number ?? raw.roundNumber),
    dimensionName:
      raw.dimension_name !== undefined ? str(raw.dimension_name) : raw.dimensionName !== undefined ? str(raw.dimensionName) : undefined,
    device: raw.device !== undefined ? str(raw.device) : undefined,
    label: raw.label !== undefined ? str(raw.label) : undefined,
    value: raw.value,
    rounds: raw.rounds,
  }
}

/** 用例项 snake_case → 域模型（metrics 双格式原样保留；域模型见 report.ts ReportCaseItem） */
function toReportCaseItem(raw: unknown): ReportCaseItem {
  const rec = (raw ?? {}) as Record<string, unknown>
  const algoResults = rec.algorithm_results ?? rec.algorithmResults
  return {
    id: str(rec.id ?? rec.case_id ?? '') ?? '',
    name: str(rec.name ?? rec.case_name ?? '') ?? '',
    description: rec.description !== undefined ? str(rec.description) : undefined,
    category: str(rec.category ?? rec.test_case_type ?? undefined),
    tags: Array.isArray(rec.tags) ? (rec.tags as unknown[]).map(String) : [],
    metrics: (rec.metrics ?? {}) as ReportCaseItem['metrics'],
    caseParams: toParamDict(rec.case_params ?? rec.caseParams),
    metricScore: (rec.metric_score ?? rec.metricScore) as ReportCaseItem['metricScore'],
    metricError: (rec.metric_error ?? rec.metricError) as ReportCaseItem['metricError'],
    results: Array.isArray(rec.results)
      ? (rec.results as import('@/domain/models/report').ReportCaseResult[])
      : [],
    audios: Array.isArray(rec.audios)
      ? (rec.audios as import('@/domain/models/report').ReportAudioItem[])
      : [],
    referenceParams: toParamDict(rec.reference_params ?? rec.referenceParams),
    algorithmResults: Array.isArray(algoResults)
      ? (algoResults as Record<string, unknown>[]).map(toAlgorithmResult)
      : undefined,
    algorithmType: str(rec.algorithm_type ?? rec.algorithmType ?? undefined),
    logs: rec.logs !== undefined ? str(rec.logs) : undefined,
    overall_status: (rec.overall_status ?? rec.overallStatus) as ReportCaseItem['overall_status'],
  }
}

// ---------------------------------------------------------------------------
// 报告详情归一（report_service 实际输出与域模型差异收敛；唯一知道后端字段的层）
// ---------------------------------------------------------------------------

/** 分组统计 {id,name} → 域模型 {category_id,category_name}（report_service 实测口径） */
function toCaseCategories(raw: unknown): ReportCaseCategory[] {
  if (!Array.isArray(raw)) return []
  return raw.map((entry) => {
    const rec = (entry ?? {}) as Record<string, unknown>
    return {
      id: rec.id as string | undefined,
      category_id: (rec.category_id as string) ?? (rec.id as string),
      category_name: String(rec.category_name ?? rec.name ?? ''),
      metrics: Array.isArray(rec.metrics)
        ? (rec.metrics as ReportMetricValue[])
        : undefined,
    }
  })
}

/** 用例标签 {id,name} → 域模型 {tag_id,tag_name}（report_service 实测口径） */
function toReportTags(raw: unknown): ReportTag[] {
  if (!Array.isArray(raw)) return []
  return raw.map((entry) => {
    const rec = (entry ?? {}) as Record<string, unknown>
    return {
      id: rec.id as string | undefined,
      tag_id: (rec.tag_id as string) ?? (rec.id as string),
      tag_name: String(rec.tag_name ?? rec.name ?? ''),
      category_id: (rec.category_id as string) ?? undefined,
      category_name: (rec.category_name as string) ?? undefined,
    }
  })
}

/** 详情摘要归一：case_categories/all_case_tags/all_tags 按 report_service 输出转域模型 */
function toReportDetailData(raw: unknown): ReportDetailData {
  const rec = (raw ?? {}) as Record<string, unknown>
  const summary = (rec.summary ?? {}) as Record<string, unknown>
  const normalizedSummary: ReportSummary = {
    ...(summary as unknown as ReportSummary),
    case_categories: toCaseCategories(summary.case_categories),
    all_case_tags: toReportTags(summary.all_case_tags),
    ...(summary.all_tags !== undefined ? { all_tags: toReportTags(summary.all_tags) } : {}),
  }
  return {
    ...(rec as unknown as ReportDetailData),
    summary: normalizedSummary,
  }
}

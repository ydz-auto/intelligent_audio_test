/**
 * Report Adapter —— Domain → DTO 请求体转换
 *
 * 显式逐字段映射，禁止 ...raw/...dto 透传（分层架构对齐 W1-A）。
 * 本层为唯一知道 snake_case 的层，Domain 字段在此显式转回后端字段名。
 */
import type {
  Report,
  ReportSummary,
  ReportResourceHeader,
  ReportListQuery,
} from '../../domain/model/report'
import type {
  ReportUpdateDto,
  ReportResourceHeaderDto,
  ReportListQueryDto,
  ReportBatchDeleteDto,
  ReportExportDto,
  GenerateTaskReportDto,
  GetCaseAveragesDto,
  ReportSearchCasesDto,
} from '../dto/reportDto'

/** 报告编辑 → ReportUpdateRequest 请求体（仅可编辑字段，显式枚举） */
export function toReportUpdateDto(report: Partial<Report>): ReportUpdateDto {
  const dto: ReportUpdateDto = {}
  if (report.name !== undefined) dto.name = report.name
  if (report.title !== undefined) dto.title = report.title
  if (report.description !== undefined) dto.description = report.description
  if (report.conclusion !== undefined) dto.conclusion = report.conclusion
  if (report.summary !== undefined) dto.summary = report.summary as unknown as Record<string, unknown>
  return dto
}

/**
 * 摘要保存（ReportUpdateSummaryField 白名单）→ snake_case 请求体。
 * 专供"只保存部分 summary 字段"的调用（报告头部编辑等），全量编辑走 toReportUpdateDto。
 * allTags 为后端遗留字段（与 all_case_tags 并存），一并透传避免丢数据。
 */
export function toReportSummaryFieldDto(
  summary: Partial<ReportSummary> & { allTags?: unknown }
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  if (summary.caseCategories !== undefined) out.case_categories = summary.caseCategories
  if (summary.allCaseTags !== undefined) out.all_case_tags = summary.allCaseTags
  if ((summary as { allTags?: unknown }).allTags !== undefined) {
    out.all_tags = (summary as { allTags?: unknown }).allTags
  }
  if (summary.resourceHeaders !== undefined) {
    out.resource_headers = summary.resourceHeaders.map(toResourceHeaderDto)
  }
  if (summary.allMetrics !== undefined) {
    out.all_metrics = summary.allMetrics.map(m => ({
      id: m.id,
      name: m.name,
      unit: m.unit,
      decimal_places: m.decimalPlaces,
    }))
  }
  if (summary.metricData !== undefined) {
    out.metric_data = summary.metricData.map(r => ({
      resource: r.resource,
      categories: r.categories.map(c => ({
        category_id: c.categoryId,
        category_name: c.categoryName,
        metrics: c.metrics.map(m => ({ id: m.id, metric: m.metric, value: m.value })),
      })),
    }))
  }
  if (summary.tagMetricData !== undefined) {
    out.tag_metric_data = summary.tagMetricData.map(r => ({
      resource: r.resource,
      tags: r.tags.map(t => ({
        tag_id: t.tagId,
        tag_name: t.tagName,
        category_id: t.categoryId,
        category_name: t.categoryName,
        metrics: t.metrics.map(m => ({ id: m.id, metric: m.metric, value: m.value })),
      })),
    }))
  }
  if (summary.rawData !== undefined) {
    out.raw_data = summary.rawData.map(g => ({
      resource: g.resource,
      metrics: g.metrics.map(m => ({ metric: m.metric, values: m.values })),
    }))
  }
  if (summary.deviceStats !== undefined) {
    out.device_stats = summary.deviceStats.map(d => ({
      id: d.id,
      name: d.name,
      model: d.model,
      type: d.type,
      system: d.system,
      system_version: d.systemVersion,
      status: d.status,
      metrics: d.metrics,
      total_cases: d.totalCases,
      completed_cases: d.completedCases,
      failed_cases: d.failedCases,
      success_rate: d.successRate,
    }))
  }
  if (summary.apiStats !== undefined) {
    out.api_stats = summary.apiStats.map(a => ({
      id: a.id,
      name: a.name,
      status: a.status,
      max_process: a.maxProcess,
      health_score: a.healthScore,
      metrics: a.metrics,
      total_cases: a.totalCases,
      completed_cases: a.completedCases,
      failed_cases: a.failedCases,
      success_rate: a.successRate,
      avg_response_time: a.avgResponseTime,
      stability: a.stability,
    }))
  }
  if (summary.caseTypeStats !== undefined) {
    out.case_type_stats = summary.caseTypeStats.map(row => ({
      group_id: row.groupId,
      group_name: row.groupName,
      metrics: row.metrics.map(m => ({ id: m.id, metric: m.metric, value: m.value })),
    }))
  }
  return out
}

/** 资源表头 Domain → DTO（逆转换辅助） */
function toResourceHeaderDto(header: ReportResourceHeader): ReportResourceHeaderDto {
  return {
    key: header.key,
    label: header.label,
    type: header.type ?? null,
    id: header.id ?? null,
    name: header.name ?? null,
    version: header.version ?? null,
    editable: header.editable ?? null,
  }
}

/** 列表查询参数 Domain → ReportListQueryDto（type → report_type 显式转） */
export function toReportListQueryDto(query: Partial<ReportListQuery>): ReportListQueryDto {
  return {
    page: query.page ?? 1,
    per_page: query.perPage ?? 20,
    sort_by: query.sortBy ?? 'created_at',
    order: query.order ?? 'desc',
    ...(query.type !== undefined ? { report_type: query.type } : {}),
    ...(query.status !== undefined ? { status: query.status } : {}),
    ...(query.keyword !== undefined ? { keyword: query.keyword } : {}),
    ...(query.startTime !== undefined ? { start_time: query.startTime } : {}),
    ...(query.endTime !== undefined ? { end_time: query.endTime } : {}),
    ...(query.algorithmType !== undefined ? { algorithm_type: query.algorithmType } : {}),
  }
}

/** 批量删除请求体（后端直接读 body.ids / body.hard_delete） */
export function toReportBatchDeleteDto(ids: Array<string | number>, hardDelete = false): ReportBatchDeleteDto {
  return { ids, hard_delete: hardDelete }
}

/** 报告导出请求体 */
export function toReportExportDto(ids: Array<string | number>, format: string): ReportExportDto {
  return { ids, format }
}

/** 生成任务报告请求体（GenerateTaskReportRequest: task_id/name/description） */
export function toGenerateTaskReportDto(
  taskId: string | number,
  name: string | null,
  description: string | null = null
): GenerateTaskReportDto {
  return {
    task_id: taskId,
    ...(name !== null && name !== undefined ? { name } : {}),
    ...(description !== null && description !== undefined ? { description } : {}),
  }
}

/** 用例平均值查询请求体（GetCaseAveragesRequest） */
export function toGetCaseAveragesDto(
  taskId: string | number,
  filters: { category?: string | null; tags?: string[]; categories?: string[]; includeUntagged?: boolean | null } = {}
): GetCaseAveragesDto {
  return {
    task_id: taskId,
    ...(filters.category !== undefined ? { category: filters.category } : {}),
    ...(filters.tags !== undefined ? { tags: filters.tags } : {}),
    ...(filters.categories !== undefined ? { categories: filters.categories } : {}),
    ...(filters.includeUntagged !== undefined ? { include_untagged: filters.includeUntagged } : {}),
  }
}

/** 报告用例搜索请求体（ReportSearchCasesRequest） */
export function toReportSearchCasesDto(body: {
  keyword?: string | null
  category?: string | null
  categories?: string[]
  includeUntagged?: boolean | null
  tags?: string[]
  metrics?: string[]
  sortBy?: string
  sortMetric?: string | null
  sortOrder?: string
  page?: number
  perPage?: number
}): ReportSearchCasesDto {
  return {
    ...(body.keyword !== undefined ? { keyword: body.keyword } : {}),
    ...(body.category !== undefined ? { category: body.category } : {}),
    ...(body.categories !== undefined ? { categories: body.categories } : {}),
    ...(body.includeUntagged !== undefined ? { include_untagged: body.includeUntagged } : {}),
    ...(body.tags !== undefined ? { tags: body.tags } : {}),
    ...(body.metrics !== undefined ? { metrics: body.metrics } : {}),
    ...(body.sortBy !== undefined ? { sort_by: body.sortBy } : {}),
    ...(body.sortMetric !== undefined ? { sort_metric: body.sortMetric } : {}),
    ...(body.sortOrder !== undefined ? { sort_order: body.sortOrder } : {}),
    page: body.page ?? 1,
    per_page: body.perPage ?? 20,
  }
}
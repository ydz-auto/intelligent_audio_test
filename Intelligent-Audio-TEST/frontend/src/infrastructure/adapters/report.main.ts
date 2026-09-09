/**
 * Report Adapter —— 摘要、主转换、列表项与对比结果转换
 *
 * 显式逐字段映射，禁止 ...raw/...dto 透传（分层架构对齐 W1-A）。
 * Enum 值不转换（type/status 保持后端原值），只转字段名。
 */
import type {
  Report,
  ReportSummary,
  ReportListItemSummary,
  ReportListItemDomain,
  ReportListData,
  CompareResult,
} from '../../domain/model/report'
import type {
  ReportDto,
  ReportListItemDto,
  ReportListItemSummaryDto,
  ReportListDataDto,
  ReportSummaryDto,
  CompareResultDto,
} from '../dto/reportDto'
import { toSafeNumber as n } from './commonAdapter'
import {
  toMetricConfig,
  toDetailedResult,
  toDeviceStat,
  toApiStat,
  toDeviceInfo,
  toApiInfo,
  toResourceHeader,
  toRawDataGroup,
  toMetricByResource,
  toTagMetricByResource,
  toCaseTypeStatRow,
  toCaseEntity,
  toMetricStat,
  toRawDataEntity,
  toFieldMappings,
} from './report.mapping'
import { s } from './report.utils'

// ===== 摘要转换 =====

/** 摘要转换（summary 字段存在才逐项映射；数组字段容忍非数组为空） */
export function toReportSummary(dto: ReportSummaryDto): ReportSummary {
  const arr = <T,>(value: T[] | Record<string, unknown> | null | undefined): T[] =>
    Array.isArray(value) ? value : []

  /** 用例分组/标签归一：后端可能返回 [{id,name}] 对象数组或字符串数组，统一归一化为 name 字符串数组（Domain 契约 string[]） */
  const toNames = (rows: unknown): string[] =>
    Array.isArray(rows)
      ? rows
          .map(r => (r !== null && typeof r === 'object' ? s((r as { name?: unknown }).name) : s(r)))
          .filter(Boolean)
      : []

  return {
    totalCases: n(dto.total_cases),
    completedCases: n(dto.completed_cases),
    failedCases: n(dto.failed_cases),
    passedCases: dto.passed_cases !== undefined ? n(dto.passed_cases) : undefined,
    passRate: dto.pass_rate !== undefined ? n(dto.pass_rate) : undefined,
    avgScore: dto.avg_score !== undefined ? n(dto.avg_score) : undefined,
    allMetrics: arr(dto.all_metrics).map(toMetricConfig),
    detailedResults: arr<Record<string, unknown>>(dto.detailed_results).map(toDetailedResult),
    deviceStats: arr(dto.device_stats).map(toDeviceStat),
    apiStats: arr(dto.api_stats).map(toApiStat),
    metrics: dto.metrics,
    rawData: arr(dto.raw_data).map(toRawDataGroup),
    metricData: arr(dto.metric_data).map(toMetricByResource),
    tagMetricData: arr(dto.tag_metric_data).map(toTagMetricByResource),
    caseTypeStats: arr(dto.case_type_stats).map(toCaseTypeStatRow),
    overallSuccessRate: dto.overall_success_rate !== undefined ? n(dto.overall_success_rate) : undefined,
    stability: dto.stability !== undefined ? n(dto.stability) : undefined,
    dimensionValues: dto.dimension_values,
    devices: (dto.devices ?? []).map(d => (typeof d === 'string' ? d : toDeviceInfo(d))),
    apis: (dto.apis ?? []).map(a => (typeof a === 'string' ? a : toApiInfo(a))),
    resourceHeaders: arr(dto.resource_headers).map(toResourceHeader),
    caseCategories: toNames(dto.case_categories),
    allCaseTags: toNames(dto.all_case_tags),
    allTags: toNames(dto.all_tags),
    resources: dto.resources ?? [],
    fieldMappings: toFieldMappings(dto.field_mappings),
  }
}

// ===== 主转换 =====

/** 报告 DTO → Report（列表项/详情通用；缺失字段容忍为 undefined） */
export function toReport(dto: Partial<ReportDto> | ReportListItemDto): Report {
  const d = dto as ReportDto & ReportListItemDto
  return {
    id: d.id,
    name: s(d.name),
    type: (d.type ?? '') as Report['type'],
    status: (d.status ?? '') as Report['status'],
    createdAt: s(d.created_at),
    updatedAt: d.updated_at ?? undefined,
    taskId: d.task_id ?? undefined,
    taskName: d.task_name ?? undefined,
    algorithmType: d.algorithm_type ?? undefined,
    description: d.description ?? undefined,
    summary: d.summary ? toReportSummary(d.summary as ReportSummaryDto) : undefined,
    detailedResults: Array.isArray(d.detailed_results)
      ? d.detailed_results.map(item => toDetailedResult(item as unknown as Record<string, unknown>))
      : undefined,
    conclusion: d.conclusion ?? undefined,
    title: d.title ?? undefined,
    config: d.config ?? undefined,
    summaries: Array.isArray(d.summaries)
      ? d.summaries.map(sm => ({
          id: sm.id,
          reportId: sm.report_id,
          metricName: sm.metric_name,
          metricValue: n(sm.metric_value),
          metadata: sm.metadata ?? {},
        }))
      : undefined,
    cases: Array.isArray(d.cases) ? d.cases.map(toCaseEntity) : undefined,
    metricStats: Array.isArray(d.metric_stats) ? d.metric_stats.map(toMetricStat) : undefined,
    rawData: Array.isArray(d.raw_data) ? d.raw_data.map(toRawDataEntity) : undefined,
  }
}

/** 报告列表项 → ReportListItemDomain（容忍聚合根形状：report_type/config.name 回退） */
export function toReportListItem(dto: ReportListItemDto): ReportListItemDomain {
  const agg = dto as ReportListItemDto & {
    report_type?: string
    config?: Record<string, unknown> | null
  }
  const configName = typeof agg.config?.name === 'string' ? agg.config.name : undefined
  const configTaskName = typeof agg.config?.task_name === 'string' ? agg.config.task_name : undefined
  const summary = dto.summary as ReportListItemSummaryDto
  const listItemSummary: ReportListItemSummary = {
    totalCases: n(summary?.total_cases),
    completedCases: n(summary?.completed_cases),
    failedCases: n(summary?.failed_cases),
    passRate: n(summary?.pass_rate),
    taskCount: summary?.task_count ?? undefined,
  }
  return {
    id: dto.id,
    name: s(dto.name ?? configName),
    type: dto.type ?? agg.report_type ?? '',
    taskId: dto.task_id ?? undefined,
    taskName: s(dto.task_name ?? configTaskName),
    algorithmType: dto.algorithm_type ?? undefined,
    summary: listItemSummary,
    description: dto.description ?? undefined,
    status: dto.status as ReportListItemDomain['status'],
    createdAt: s(dto.created_at),
    updatedAt: dto.updated_at ?? undefined,
  }
}

/**
 * 列表响应 → ReportListData（camelCase）。
 * 容忍 report_service ListReports 的精简形状 {items, page, page_size}：
 * total 回退 items 长度、pages 回退 1、per_page 回退 page_size。
 */
export function toReportListData(dto: ReportListDataDto): ReportListData {
  const partial = dto as ReportListDataDto & { page_size?: number }
  const items = (partial.items ?? []).map(toReportListItem)
  return {
    items,
    total: n(partial.total, items.length),
    page: n(partial.page, 1),
    perPage: n(partial.per_page, n(partial.page_size, items.length)),
    pages: n(partial.pages, 1),
  }
}

/** 对比响应 → CompareResult（Enum 值不转换） */
export function toCompareResult(dto: CompareResultDto): CompareResult {
  return {
    reportId: dto.report_id ?? undefined,
    id: dto.id ?? undefined,
    reportKey: dto.report_key ?? undefined,
    status: dto.status ?? undefined,
    differences: dto.differences ?? undefined,
  }
}
/**
 * 报告统计分析 Adapter —— snake_case ⇄ camelCase 唯一落点
 *
 * 请求体：Domain（camelCase）→ DTO（snake_case）
 * 响应：DTO（snake_case）→ Domain（camelCase）
 */
import type {
  ReportStatisticsQuery,
  ReportStatisticsTrendQuery,
  GenerateReportParams,
  ReportStatisticsData,
  ReportStatisticsOverview,
  ReportStatisticsDetailItem,
  ReportStatisticsChart,
  ReportStatisticsAnomalyItem,
  ReportStatisticsTrendData,
  ReportTimeTrendItem,
  ReportDimensionTrendItem,
} from '../../domain/model/reportStatistics'
import type {
  ReportStatisticsQueryDto,
  ReportStatisticsTrendQueryDto,
  GenerateStatisticsReportDto,
  ReportStatisticsDataDto,
  ReportStatisticsOverviewDto,
  ReportStatisticsDetailItemDto,
  ReportStatisticsChartDto,
  ReportStatisticsAnomalyItemDto,
  ReportStatisticsTrendDataDto,
  ReportTimeTrendItemDto,
  ReportDimensionTrendItemDto,
} from '../dto/reportStatisticsDto'

/** 日期输入归一化：date-only（YYYY-MM-DD）→ ISO 8601 开始时刻（含时分秒） */
function toStartTime(value: string): string {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value
}

/** 日期输入归一化：date-only（YYYY-MM-DD）→ ISO 8601 结束时刻（含当日全天） */
function toEndTime(value: string): string {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T23:59:59` : value
}

/** 统计分析查询参数 Domain → DTO（dimension 缺省交由后端默认 time） */
export function toReportStatisticsQueryDto(query: ReportStatisticsQuery): ReportStatisticsQueryDto {
  return {
    ...(query.dimension !== undefined ? { dimension: query.dimension } : {}),
    ...(query.startTime ? { start_time: toStartTime(query.startTime) } : {}),
    ...(query.endTime ? { end_time: toEndTime(query.endTime) } : {}),
    ...(query.algorithmType ? { algorithm_type: query.algorithmType } : {}),
  }
}

/** 趋势分析查询参数 Domain → DTO */
export function toReportStatisticsTrendQueryDto(query: ReportStatisticsTrendQuery): ReportStatisticsTrendQueryDto {
  return {
    trend_type: query.trendType,
    ...(query.metric ? { metric: query.metric } : {}),
    ...(query.startTime ? { start_time: toStartTime(query.startTime) } : {}),
    ...(query.endTime ? { end_time: toEndTime(query.endTime) } : {}),
  }
}

/** 报表生成参数 Domain → DTO（time_range 对象形态，缺省留空对象） */
export function toGenerateStatisticsReportDto(params: GenerateReportParams): GenerateStatisticsReportDto {
  return {
    report_type: params.reportType,
    format: params.format,
    ...(params.content ? { content: params.content } : {}),
    time_range: {
      ...(params.startTime ? { start_time: toStartTime(params.startTime) } : {}),
      ...(params.endTime ? { end_time: toEndTime(params.endTime) } : {}),
    },
  }
}

function toOverview(dto: ReportStatisticsOverviewDto): ReportStatisticsOverview {
  return {
    reportCount: dto.report_count,
    completedReports: dto.completed_reports,
    totalCases: dto.total_cases,
    completedCases: dto.completed_cases,
    failedCases: dto.failed_cases,
    passRate: dto.pass_rate,
    duration: dto.duration,
  }
}

function toDetailItem(dto: ReportStatisticsDetailItemDto): ReportStatisticsDetailItem {
  return {
    group: dto.group,
    metric: dto.metric,
    deviceType: dto.device_type,
    deviceCount: dto.device_count,
    reportCount: dto.report_count,
    completedReports: dto.completed_reports,
    totalCases: dto.total_cases,
    completedCases: dto.completed_cases,
    failedCases: dto.failed_cases,
    passRate: dto.pass_rate,
    duration: dto.duration,
    averageValue: dto.average_value,
    min: dto.min,
    max: dto.max,
  }
}

function toChart(dto: ReportStatisticsChartDto): ReportStatisticsChart {
  return {
    categories: dto.categories ?? [],
    series: (dto.series ?? []).map(s => ({ name: s.name, data: s.data ?? [] })),
  }
}

function toAnomalyItem(dto: ReportStatisticsAnomalyItemDto): ReportStatisticsAnomalyItem {
  return {
    type: dto.type,
    reportId: dto.report_id,
    reportName: dto.report_name,
    message: dto.message,
    value: dto.value,
  }
}

/** 统计分析响应 DTO → Domain */
export function toReportStatistics(dto: ReportStatisticsDataDto): ReportStatisticsData {
  return {
    dimension: dto.dimension as ReportStatisticsData['dimension'],
    overview: toOverview(dto.overview),
    detail: (dto.detail ?? []).map(toDetailItem),
    chart: toChart(dto.chart),
    anomaly: (dto.anomaly ?? []).map(toAnomalyItem),
  }
}

function toTimeTrendItem(dto: ReportTimeTrendItemDto): ReportTimeTrendItem {
  return {
    date: dto.date,
    reportCount: dto.report_count,
    totalCases: dto.total_cases,
    passRate: dto.pass_rate,
    duration: dto.duration,
  }
}

function toDimensionTrendItem(dto: ReportDimensionTrendItemDto): ReportDimensionTrendItem {
  return {
    metric: dto.metric,
    points: (dto.points ?? []).map(p => ({ date: p.date, value: p.value })),
  }
}

/** 趋势分析响应 DTO → Domain */
export function toReportStatisticsTrend(dto: ReportStatisticsTrendDataDto): ReportStatisticsTrendData {
  return {
    trendType: dto.trend_type as ReportStatisticsTrendData['trendType'],
    metric: dto.metric,
    timeTrend: (dto.time_trend ?? []).map(toTimeTrendItem),
    dimensionTrend: (dto.dimension_trend ?? []).map(toDimensionTrendItem),
  }
}

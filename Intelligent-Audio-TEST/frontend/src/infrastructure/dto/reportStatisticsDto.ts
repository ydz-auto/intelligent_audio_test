/**
 * 报告统计分析 DTO —— snake_case
 * 仅 infrastructure 层（adapters/api）允许 import；业务层不得直接接触。
 * 契约来源：api_gateway/schemas/report.py + report_service/statistics_service.py
 * （doc/接口文档/06_报告管理.md §8）。
 */

/** GET /reports/statistics 查询参数（ReportStatisticsQuery） */
export interface ReportStatisticsQueryDto {
  dimension?: string
  start_time?: string
  end_time?: string
  algorithm_type?: string
}

/** GET /reports/statistics/trend 查询参数（ReportStatisticsTrendQuery） */
export interface ReportStatisticsTrendQueryDto {
  trend_type?: string
  metric?: string
  start_time?: string
  end_time?: string
}

/** POST /reports/statistics/report 请求体（GenerateStatisticsReportRequest） */
export interface GenerateStatisticsReportDto {
  report_type: string
  content?: string
  format: string
  time_range: {
    start_time?: string
    end_time?: string
  }
}

/** 总览聚合（overview） */
export interface ReportStatisticsOverviewDto {
  report_count: number
  completed_reports: number
  total_cases: number
  completed_cases: number
  failed_cases: number
  pass_rate: number
  duration: number
}

/** 明细行（detail 元素；time/task_type 含 group，device_type 含 device_type/device_count，evaluation_metric 含 metric/average_value/min/max） */
export interface ReportStatisticsDetailItemDto {
  group?: string
  metric?: string
  device_type?: string
  device_count?: number
  report_count: number
  completed_reports?: number
  total_cases: number
  completed_cases: number
  failed_cases: number
  pass_rate: number
  duration: number
  average_value?: number
  min?: number
  max?: number
}

/** 图表序列（chart.series 元素） */
export interface ReportStatisticsChartSeriesDto {
  name: string
  data: number[]
}

/** 图表数据（chart） */
export interface ReportStatisticsChartDto {
  categories: string[]
  series: ReportStatisticsChartSeriesDto[]
}

/** 异常项（anomaly 元素） */
export interface ReportStatisticsAnomalyItemDto {
  type: string
  report_id: number
  report_name: string
  message: string
  value: number
}

/** 统计分析响应 data（GET /reports/statistics） */
export interface ReportStatisticsDataDto {
  dimension: string
  overview: ReportStatisticsOverviewDto
  detail: ReportStatisticsDetailItemDto[]
  chart: ReportStatisticsChartDto
  anomaly: ReportStatisticsAnomalyItemDto[]
}

/** 时间趋势点（time_trend 元素） */
export interface ReportTimeTrendItemDto {
  date: string
  report_count: number
  total_cases: number
  pass_rate: number
  duration: number
}

/** 维度趋势序列（dimension_trend 元素） */
export interface ReportDimensionTrendItemDto {
  metric: string
  points: Array<{ date: string; value: number }>
}

/** 趋势分析响应 data（GET /reports/statistics/trend） */
export interface ReportStatisticsTrendDataDto {
  trend_type: string
  metric?: string
  time_trend: ReportTimeTrendItemDto[]
  dimension_trend: ReportDimensionTrendItemDto[]
}

/** 报表生成二进制下载结构（BFF 转 Blob 下载，见 report_bp._handle） */
export interface GeneratedReportDto {
  filename: string
  format: string
  content_base64: string
  mime_type: string
}

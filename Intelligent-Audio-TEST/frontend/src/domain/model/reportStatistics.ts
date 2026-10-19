/**
 * 报告统计分析领域模型 —— camelCase
 *
 * 真实后端契约（INT-791，doc/接口文档/06_报告管理.md §8）：
 * - GET  /reports/statistics        → { dimension, overview, detail, chart, anomaly }
 * - GET  /reports/statistics/trend  → { trend_type, metric?, time_trend, dimension_trend }
 * - POST /reports/statistics/report → 二进制下载（Blob）
 */

/** 统计维度（dimension） */
export type ReportStatisticsDimension = 'time' | 'task_type' | 'device_type' | 'evaluation_metric'

/** 趋势类型（trend_type） */
export type ReportTrendType = 'time' | 'dimension'

/** 报表类型（report_type） */
export type ReportStatisticsReportType =
  | 'report_count'
  | 'case_execution'
  | 'evaluation_metric'
  | 'device_performance'

/** 报表格式（format） */
export type ReportStatisticsFormat = 'csv' | 'excel' | 'pdf' | 'html'

/** 总览聚合（overview） */
export interface ReportStatisticsOverview {
  reportCount: number
  completedReports: number
  totalCases: number
  completedCases: number
  failedCases: number
  passRate: number
  duration: number
}

/** 明细行（detail 元素：time/task_type 含 group；device_type 含 deviceType/deviceCount；evaluation_metric 含 metric/averageValue/min/max） */
export interface ReportStatisticsDetailItem {
  group?: string
  metric?: string
  deviceType?: string
  deviceCount?: number
  reportCount: number
  completedReports?: number
  totalCases: number
  completedCases: number
  failedCases: number
  passRate: number
  duration: number
  averageValue?: number
  min?: number
  max?: number
}

/** 图表序列 */
export interface ReportStatisticsChartSeries {
  name: string
  data: number[]
}

/** 图表数据（chart：categories + series，可直接转 Chart.js 数据源） */
export interface ReportStatisticsChart {
  categories: string[]
  series: ReportStatisticsChartSeries[]
}

/** 异常项（anomaly 元素；type=no_cases|low_pass_rate|data_error，message 为中文文案） */
export interface ReportStatisticsAnomalyItem {
  type: string
  reportId: number
  reportName: string
  message: string
  value: number
}

/** 统计分析响应（GET /reports/statistics） */
export interface ReportStatisticsData {
  dimension: ReportStatisticsDimension
  overview: ReportStatisticsOverview
  detail: ReportStatisticsDetailItem[]
  chart: ReportStatisticsChart
  anomaly: ReportStatisticsAnomalyItem[]
}

/** 时间趋势点（time_trend 元素） */
export interface ReportTimeTrendItem {
  date: string
  reportCount: number
  totalCases: number
  passRate: number
  duration: number
}

/** 维度趋势点（dimension_trend.points 元素） */
export interface ReportDimensionTrendPoint {
  date: string
  value: number
}

/** 维度趋势序列（dimension_trend 元素） */
export interface ReportDimensionTrendItem {
  metric: string
  points: ReportDimensionTrendPoint[]
}

/** 趋势分析响应（GET /reports/statistics/trend） */
export interface ReportStatisticsTrendData {
  trendType: ReportTrendType
  metric?: string
  timeTrend: ReportTimeTrendItem[]
  dimensionTrend: ReportDimensionTrendItem[]
}

/** 统计分析查询参数（GET /reports/statistics） */
export interface ReportStatisticsQuery {
  dimension?: ReportStatisticsDimension
  startTime?: string
  endTime?: string
  algorithmType?: string
}

/** 趋势分析查询参数（GET /reports/statistics/trend） */
export interface ReportStatisticsTrendQuery {
  trendType: ReportTrendType
  metric?: string
  startTime?: string
  endTime?: string
}

/** 报表生成参数（POST /reports/statistics/report） */
export interface GenerateReportParams {
  reportType: ReportStatisticsReportType
  content?: string
  format: ReportStatisticsFormat
  startTime?: string
  endTime?: string
}

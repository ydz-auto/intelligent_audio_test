/**
 * 报告统计分析领域类型（domain 层；15_报告域.md §2.2）。
 * 统计维度枚举由 application/features 共享，避免 application→interfaces 反向依赖。
 * INT-643 接线：POST /reports/case-averages 响应域模型（snake→camel 转换只在 infrastructure 层，
 * 契约对位 api_gateway report_bp.py:106 get_case_averages_by_filters + report_service stats_mixin）。
 */
export type StatisticDimension = 'time' | 'task_type' | 'device_type' | 'metric'

/** 用例平均值项（case-averages overall_averages 项：{id, metric, value}） */
export interface ReportCaseAverageMetric {
  id?: number | string
  metric: string
  value: number
}

/** 资源级指标数据组（case-averages metric_data 项；flatten_metric_data 双格式兼容） */
export interface ReportCaseAverageMetricGroup {
  resource: string
  metrics?: ReportCaseAverageMetric[]
  categories?: {
    categoryId?: number | string
    categoryName: string
    metrics: ReportCaseAverageMetric[]
  }[]
}

/** POST /reports/case-averages 响应（GetCaseAveragesRequest；Vue reportsApi.getCaseAveragesByFilters 同套契约） */
export interface ReportCaseAveragesData {
  totalCases: number
  totalResults: number
  overallAverages: ReportCaseAverageMetric[]
  metricData: ReportCaseAverageMetricGroup[]
  resources: string[]
  resourceHeaders?: string[]
  rawData?: unknown
  normalDistribution?: unknown
  filters?: { category?: string | null; tags?: string[] }
}

/**
 * Benchmark 报告 DTO —— snake_case，仅 adapters/api 允许 import
 *
 * 字段口径对应 report_service/infrastructure/persistence/benchmark_repository.py
 * _benchmark_report_dict / _row_dict（INT-481 第五表 benchmark_reports 实测序列化结果），
 * 禁止在此层做 camelCase。
 */

/** 排行快照行 DTO（_row_dict） */
export interface BenchmarkSnapshotRowDto {
  id: number
  source: string
  published_task_id: number | null
  published_task_version: number | null
  report_id: number | null
  baseline_id: number | null
  subject_name: string
  subject_type: string
  device_type: string | null
  benchmark_suite: string
  category: string
  metric_code: string
  metric_name: string
  metric_value: number
  unit: string
  direction: string
  rank: number
  total: number
  percentile: number | null
  score100: number | null
  gap_best: number | null
  gap_median: number | null
  delta_external: number | null
  scenario_key: string
  computed_at: string | null
}

/** 排行快照（发布时点定格） */
export interface BenchmarkReportSnapshotDto {
  filters: {
    suite: string
    category: string
    source: string
  }
  counts: {
    published_task_count: number
    subject_count: number
    metric_count: number
    row_count: number
  }
  rows: BenchmarkSnapshotRowDto[]
}

/** Benchmark 报告发布记录 DTO（_benchmark_report_dict） */
export interface BenchmarkReportRecordDto {
  id: number
  report_id: number
  task_id: number | null
  suite: string
  category: string
  source: string
  algorithm_set: string
  published_task_count: number
  subject_count: number
  metric_count: number
  ranking_data?: BenchmarkReportSnapshotDto | null
  version: number
  published_by: string
  published_at: string | null
  created_at: string | null
  updated_at: string | null
}

/** Benchmark 报告列表信封（/benchmarks/reports GET 契约；列表项不携带 ranking_data） */
export interface BenchmarkReportListDataDto {
  items: BenchmarkReportRecordDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** 发布 Benchmark 报告请求体（网关 BenchmarkReportCreateRequest 契约，全可选 = 全量快照） */
export interface BenchmarkReportCreateDto {
  task_id?: number
  suite?: string
  category?: string
  source?: string
  algorithm_set?: string
  name?: string
  description?: string
}

/** Benchmark 报告列表查询参数（snake_case，网关 list_reports 契约） */
export interface BenchmarkReportListQueryDto {
  suite?: string
  category?: string
  source?: string
  task_id?: number
  page?: number
  per_page?: number
}

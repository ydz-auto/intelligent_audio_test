/**
 * Benchmark DTO —— snake_case，仅 adapters/api 允许 import
 *
 * 字段口径对应 report_service/infrastructure/persistence/benchmark_repository.py
 * _row_dict / _mapping_to_entity 实测序列化结果，禁止在此层做 camelCase。
 */
export interface BenchmarkRankingRowDto {
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

/** 排行列表信封（INT-297：单页全量） */
export interface BenchmarkRankingListDataDto {
  items: BenchmarkRankingRowDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** 指标映射 DTO（metric-mappings 清单项） */
export interface MetricMappingDto {
  id: number
  dimension_name: string
  metric_code: string
  metric_name: string
  unit: string
  direction: string
  scenario_tags: string[]
  active: boolean
}

/** 指标映射列表信封 */
export interface MetricMappingListDataDto {
  items: MetricMappingDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** 排行查询参数（snake_case，网关 benchmark_bp.get_ranking 契约） */
export interface BenchmarkRankingQueryDto {
  suite?: string
  category?: string
  metric_code?: string
  source?: string
  published_task_id?: number
  subject_name?: string
}

/** 排行计算请求体（网关 BenchmarkRankingComputeRequest 契约，全可选=全量重算） */
export interface BenchmarkComputeRequestDto {
  suite?: string
  category?: string
  source?: string
}

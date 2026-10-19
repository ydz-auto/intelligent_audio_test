/**
 * Benchmark 排行 DTO（infrastructure/dto 层——snake_case 唯一出现层；14_benchmark排行.md §9）。
 * 形态对照 api_gateway/schemas/benchmark.py + report_service BenchmarkRanking ReadModel
 * （benchmark_repository._row_dict / _mapping_to_entity 实测序列化结果），
 * 由 infrastructure/adapters/benchmarkAdapter.ts 唯一转换为 camelCase Domain。
 * INT-730 接线：GET /benchmarks/ranking、/ranking/subjects、/metric-mappings、
 * POST /ranking/compute 全部经 client.ts 真实端点（信封 data 解包后即本层 ListDataDto）。
 */
import type {
  BenchmarkCategory,
  BenchmarkDeviceType,
  BenchmarkDirection,
  BenchmarkSource,
  BenchmarkSubjectType,
} from '@/domain/models/benchmark'

/** 排行行 DTO（report_service BenchmarkRanking ReadModel 返回形态） */
export interface BenchmarkRankingDto {
  id: number
  source: BenchmarkSource
  category: BenchmarkCategory
  metric_code: string
  metric_name: string
  unit: string
  direction: BenchmarkDirection
  rank: number
  total: number
  percentile: number | null
  score100: number | null
  subject_name: string
  subject_type: BenchmarkSubjectType
  device_type: BenchmarkDeviceType | null
  benchmark_suite: string
  scenario_key: string
  metric_value: number
  gap_best: number | null
  gap_median: number | null
  delta_external: number | null
  published_task_id: number | null
  published_task_version: number | null
  report_id: number | null
  baseline_id: number | null
  computed_at: string
}

/** 指标映射 DTO（GET /metric-mappings 返回形态） */
export interface BenchmarkMetricMappingDto {
  id: number
  dimension_name: string
  metric_code: string
  metric_name: string
  unit: string
  direction: BenchmarkDirection
  scenario_tags: string[]
  active: boolean
}

/** 排行列表信封 data（INT-297：单页全量 page=1, pages=1） */
export interface BenchmarkRankingListDataDto {
  items: BenchmarkRankingDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** 指标映射列表信封 data（INT-297：单页全量） */
export interface BenchmarkMetricMappingListDataDto {
  items: BenchmarkMetricMappingDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** 被测主体去重清单信封 data（GET /ranking/subjects 返回形态——
 *   report_service list_ranking_subjects 实测为 **string[]**，非 {subject_name} 对象） */
export interface BenchmarkSubjectListDataDto {
  items: string[]
  total: number
  page: number
  per_page: number
  pages: number
}

/**
 * Benchmark 域 DTO 类型（infrastructure 层，与 benchmarkApi.ts 同层）。
 *
 * 字段形态对照 report_service ReadModel（benchmark_models.py BenchmarkRanking
 * 实测字段）+ api_gateway/schemas/benchmark.py——**snake_case DTO 形态**，
 * 由 infrastructure/adapters/benchmarkAdapter.ts 唯一转换为 camelCase Domain
 * （14_benchmark排行.md §9）。
 *
 * 历史：这些类型原先住在 infrastructure/mock/benchmark-mock.ts 里（文件名带 mock
 * 但实际只导出类型 = 命名误导，INT-1595）。运行期 mock 常量接线后已无引用，随文件删除；
 * 类型本身搬到本文件，引用方不再经由 mock 目录。
 */
import type {
  BenchmarkCategory,
  BenchmarkDeviceType,
  BenchmarkDirection,
  BenchmarkSource,
  BenchmarkSubjectType,
} from '@/domain/models/benchmark'

/** 排行 DTO 行（后端 benchmark_rankings ReadModel 返回形态） */
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

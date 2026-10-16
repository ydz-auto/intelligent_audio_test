/**
 * Benchmark 排行 HTTP 客户端桩（infrastructure 层，唯一知 snake_case 的层之一）。
 * 红线④：数据一律 mock 常量，不接真实后端——各函数返回 mock DTO（snake_case），
 * DTO→Domain 转换由 adapters/benchmarkAdapter.ts 唯一承担（14_benchmark排行.md §9）。
 * TODO(API 接线): 换 http 客户端统一出口（src/infrastructure/http），参数原样透传：
 *   GET  /api/v1/benchmarks/ranking        ?suite=&category=&metricCode=&source=&publishedTaskId=&subjectName=
 *   GET  /api/v1/benchmarks/ranking/subjects ?suite=
 *   GET  /api/v1/benchmarks/metric-mappings  ?activeOnly=
 *   POST /api/v1/benchmarks/ranking/compute （Body: { suite?, category?, source? }）
 */
import type {
  BenchmarkEnvelope,
  BenchmarkMetricMappingDto,
  BenchmarkRankingDto,
  BenchmarkSubjectDto,
} from '@/infrastructure/mock/benchmark-mock'
import {
  MOCK_BENCHMARK_METRIC_MAPPINGS,
  MOCK_BENCHMARK_RANKING_RESPONSE,
  MOCK_BENCHMARK_SUBJECTS,
} from '@/infrastructure/mock/benchmark-mock'

export interface RankingQueryParams {
  suite?: string
  category?: string
  metricCode?: string
  source?: string
  publishedTaskId?: number | null
  subjectName?: string
}

/** GET /api/v1/benchmarks/ranking（排行主查询；INT-297 信封单页全量） */
export async function fetchBenchmarkRanking(
  params: RankingQueryParams
): Promise<BenchmarkEnvelope<BenchmarkRankingDto>> {
  void params // TODO(API 接线): 查询参数透传后端，mock 阶段全量返回由 application 层筛选
  return MOCK_BENCHMARK_RANKING_RESPONSE
}

/** GET /api/v1/benchmarks/ranking/subjects（参与排行的被测主体去重清单） */
export async function fetchBenchmarkRankingSubjects(
  suite?: string
): Promise<BenchmarkEnvelope<BenchmarkSubjectDto>> {
  void suite
  return {
    success: true,
    message: 'ok',
    data: {
      items: MOCK_BENCHMARK_SUBJECTS,
      total: MOCK_BENCHMARK_SUBJECTS.length,
      page: 1,
      per_page: MOCK_BENCHMARK_SUBJECTS.length || 1,
      pages: 1,
    },
    code: 0,
  }
}

/** GET /api/v1/benchmarks/metric-mappings?activeOnly=true（指标筛选下拉数据源） */
export async function fetchBenchmarkMetricMappings(
  activeOnly = true
): Promise<BenchmarkEnvelope<BenchmarkMetricMappingDto>> {
  void activeOnly
  return {
    success: true,
    message: 'ok',
    data: {
      items: MOCK_BENCHMARK_METRIC_MAPPINGS,
      total: MOCK_BENCHMARK_METRIC_MAPPINGS.length,
      page: 1,
      per_page: MOCK_BENCHMARK_METRIC_MAPPINGS.length || 1,
      pages: 1,
    },
    code: 0,
  }
}

/** POST /api/v1/benchmarks/ranking/compute（全量重算排行；mock 阶段模拟成功） */
export async function computeBenchmarkRanking(params: {
  suite?: string
  category?: string
  source?: string
}): Promise<{ success: boolean; message: string; code: number }> {
  void params
  return { success: true, message: 'ok', code: 0 }
}

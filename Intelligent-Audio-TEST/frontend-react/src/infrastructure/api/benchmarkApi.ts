/**
 * Benchmark 排行 HTTP 客户端（infrastructure/api 层，唯一知 snake_case 的层之一）。
 * INT-730 接线：mock → 真实端点，全部经 client.ts 统一 fetch 封装（INT-605 基座）；
 * DTO→Domain 转换由 adapters/benchmarkAdapter.ts 唯一承担（14_benchmark排行.md §9）。
 *
 * 端点契约（api_gateway/routes/benchmark_bp.py + report_service BenchmarkConfigService）：
 *   GET  /api/v1/benchmarks/ranking         ?suite=&category=&metricCode=&source=&publishedTaskId=&subjectName=
 *   GET  /api/v1/benchmarks/ranking/subjects ?suite=
 *   GET  /api/v1/benchmarks/metric-mappings  ?activeOnly=
 *   POST /api/v1/benchmarks/ranking/compute （Body: { suite?, category?, source? }）
 * 排行查询参数 metricCode / publishedTaskId / subjectName 后端 alias 兼容两拼写
 * （benchmark_service.py:194/196 实测），前端直接发 camelCase。
 */
import { request } from '@/infrastructure/api/client'
import type {
  BenchmarkMetricMappingListDataDto,
  BenchmarkRankingDto,
  BenchmarkRankingListDataDto,
  BenchmarkSubjectListDataDto,
} from '@/infrastructure/dto/benchmark.dto'

export interface RankingQueryParams {
  suite?: string
  category?: string
  metricCode?: string
  source?: string
  publishedTaskId?: number | null
  subjectName?: string
}

/** GET /api/v1/benchmarks/ranking（排行主查询；INT-297 信封单页全量，client 解包 data） */
export async function fetchBenchmarkRanking(
  params: RankingQueryParams
): Promise<BenchmarkRankingListDataDto | null> {
  return request<BenchmarkRankingListDataDto>('GET', '/benchmarks/ranking', undefined, {
    params: { ...params },
  })
}

/** GET /api/v1/benchmarks/ranking/subjects（参与排行的被测主体去重清单，items 为 string[]） */
export async function fetchBenchmarkRankingSubjects(
  suite?: string
): Promise<BenchmarkSubjectListDataDto | null> {
  return request<BenchmarkSubjectListDataDto>(
    'GET',
    '/benchmarks/ranking/subjects',
    undefined,
    { params: suite ? { suite } : {} }
  )
}

/** GET /api/v1/benchmarks/metric-mappings?activeOnly=true（指标筛选下拉数据源） */
export async function fetchBenchmarkMetricMappings(
  activeOnly = true
): Promise<BenchmarkMetricMappingListDataDto | null> {
  return request<BenchmarkMetricMappingListDataDto>(
    'GET',
    '/benchmarks/metric-mappings',
    undefined,
    { params: { activeOnly } }
  )
}

/** POST /api/v1/benchmarks/ranking/compute（全量重算排行；失败抛 ApiError，调用方 toast） */
export async function computeBenchmarkRanking(params: {
  suite?: string
  category?: string
  source?: string
}): Promise<{ success: boolean; message: string }> {
  await request('POST', '/benchmarks/ranking/compute', params)
  return { success: true, message: 'ok' }
}

/** 排行行 DTO 类型再导出（application 层 mapRankingRowDto 输入签名用） */
export type { BenchmarkRankingDto }

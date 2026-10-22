/**
 * Benchmark 排行 HTTP 客户端（infrastructure 层，唯一知 snake_case 的层之一）。
 * 接线 INT-642：统一经基座 client.ts（INT-605）访问真实后端端点（benchmark_bp.py），
 * 不再返回 mock 常量。DTO→Domain 转换由 adapters/benchmarkAdapter.ts 唯一承担
 * （14_benchmark排行.md §9）；client 信封解包后本层只透出 INT-297 单页全量列表 data。
 *
 * 端点契约（查询参数原样透传；client 自动剔除 undefined/null）：
 *   GET  /api/v1/benchmarks/ranking        ?suite=&category=&metricCode=&source=&publishedTaskId=
 *   GET  /api/v1/benchmarks/ranking/subjects ?suite=
 *   GET  /api/v1/benchmarks/metric-mappings  ?activeOnly=
 *   POST /api/v1/benchmarks/ranking/compute （Body: { suite?, category?, source? }）
 *
 * 说明：subjectName 不在发给后端的查询参数内——后端为精确匹配，而主体搜索是
 * 联想输入（防抖 300ms 写 URL，未选中前是局部串），精确匹配会打空列表；主体
 * 子串筛选由 application 层 filterRankingRows 在 Domain 行上承担（与 mock 阶段同口径）。
 */
import type { BenchmarkMetricMappingDto, BenchmarkRankingDto } from '@/infrastructure/mock/benchmark-mock'
import { request } from '@/infrastructure/api/client'

export interface RankingQueryParams {
  suite?: string
  category?: string
  metricCode?: string
  source?: string
  publishedTaskId?: number | null
}

/** INT-297 列表信封的 data 段（后端单页全量：page=1, pages=1） */
export interface BenchmarkListData<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** GET /api/v1/benchmarks/ranking（排行主查询；query 透传后端精确筛选） */
export async function fetchBenchmarkRanking(
  params: RankingQueryParams
): Promise<BenchmarkListData<BenchmarkRankingDto>> {
  return request<BenchmarkListData<BenchmarkRankingDto>>(
    'GET',
    '/benchmarks/ranking',
    undefined,
    {
      // 内联对象字面量以匹配 ApiRequestOptions.params: Record<string, unknown>
      // （undefined/null 由 client 剔除）
      params: {
        suite: params.suite,
        category: params.category,
        metricCode: params.metricCode,
        source: params.source,
        publishedTaskId: params.publishedTaskId,
      },
      // INT-1225：/rankings 为公开路由，匿名/会话失效 401 不触发 sessionExpired
      // 整页跳登录——由页面按 14_benchmark排行.md §5.1 权限空态/错误态降级。
      skipAuthRedirect: true,
    }
  )
}

/** GET /api/v1/benchmarks/ranking/subjects（参与排行的被测主体去重清单；后端返回纯字符串数组） */
export async function fetchBenchmarkRankingSubjects(
  suite?: string
): Promise<BenchmarkListData<string>> {
  return request<BenchmarkListData<string>>(
    'GET',
    '/benchmarks/ranking/subjects',
    undefined,
    { params: { suite }, skipAuthRedirect: true }
  )
}

/** GET /api/v1/benchmarks/metric-mappings?activeOnly=true（指标筛选下拉数据源） */
export async function fetchBenchmarkMetricMappings(
  activeOnly = true
): Promise<BenchmarkListData<BenchmarkMetricMappingDto>> {
  return request<BenchmarkListData<BenchmarkMetricMappingDto>>(
    'GET',
    '/benchmarks/metric-mappings',
    undefined,
    { params: { activeOnly }, skipAuthRedirect: true }
  )
}

/**
 * POST /api/v1/benchmarks/ranking/compute（全量重算排行）。
 * 业务失败由 client 抛 ApiError（httpStatus=400 + 中文 message），调用方 mutation 兜住；
 * 成功仅需确认不抛错（返回 data 段，前端不消费）。
 */
export async function computeBenchmarkRanking(params: {
  suite?: string
  category?: string
  source?: string
}): Promise<void> {
  await request('POST', '/benchmarks/ranking/compute', params)
}

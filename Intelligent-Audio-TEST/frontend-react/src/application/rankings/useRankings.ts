/**
 * 排行榜主查询 hook（application 层，对位 newAPI use-rankings.ts）。
 * queryKey=['benchmarks','ranking',filters]；staleTime 5min；
 * placeholderData: keepPreviousData（切筛选 non-blocking 保留旧数据）。
 * 接线 INT-642：后端按 suite/category/metricCode/source 精确筛选（查询参数透传）；
 * 主体搜索为联想输入（局部串），不发给后端（后端精确匹配会打空列表），
 * 子串筛选仍由 filterRankingRows 在 Domain 行上承担（与 mock 阶段同口径）。
 */
import { useQuery } from '@tanstack/react-query'

import type { RankingFilters, RankingGroup } from '@/domain/models/benchmark'
import { fetchBenchmarkRanking } from '@/infrastructure/api/benchmarkApi'
import {
  filterRankingRows,
  mapRankingRowDto,
} from '@/infrastructure/adapters/benchmarkAdapter'
import { groupRankings } from '@/application/rankings/groupRankings'

export interface RankingQueryResult {
  /** 全部 Domain 行（未筛选，供 测试集 Select 选项去重） */
  rows: ReturnType<typeof mapRankingRowDto>[]
  /** 当前筛选下的指标组（category 由页签锁定，组内 rank 升序） */
  groups: RankingGroup[]
  /** 当前数据去重后的测试集清单（「全部测试集」之外的下拉选项） */
  suites: string[]
  isFetching: boolean
  /** 首访加载（无旧数据） */
  isLoading: boolean
  isError: boolean
  errorMessage: string | null
  /** 手动重试（错误态「重试」按钮，对齐旧 Vue store.load()） */
  refetch: () => void
}

export function useRankings(
  filters: RankingFilters,
  enabled: boolean
): RankingQueryResult {
  const query = useQuery({
    queryKey: ['benchmarks', 'ranking', filters],
    queryFn: async () => {
      const data = await fetchBenchmarkRanking({
        suite: filters.suite || undefined,
        category: filters.category || undefined,
        metricCode: filters.metricCode || undefined,
        source: filters.source || undefined,
      })
      if (!data) {
        throw new Error('查询排行失败，请稍后重试')
      }
      return data.items.map(mapRankingRowDto)
    },
    staleTime: 5 * 60_000,
    placeholderData: (previous) => previous,
    enabled,
  })

  const rows = query.data ?? []
  const filtered = filterRankingRows(rows, filters)
  const groups = groupRankings(filtered)
  const suites = [...new Set(rows.map((row) => row.benchmarkSuite))].sort()

  return {
    rows,
    groups,
    suites,
    isFetching: query.isFetching,
    isLoading: query.isLoading && !query.data,
    isError: query.isError,
    errorMessage: resolveErrorMessage(query.error),
    refetch: () => void query.refetch(),
  }
}

/** ApiError 优先展示中文 userMessage（服务端 message 可能为空，如 403 detail 兜底） */
function resolveErrorMessage(error: unknown): string | null {
  if (error instanceof Error) {
    const apiError = error as { userMessage?: string }
    if (typeof apiError.userMessage === 'string' && apiError.userMessage) {
      return apiError.userMessage
    }
    return error.message || null
  }
  return null
}

/**
 * 排行榜主查询 hook（application 层，对位 newAPI use-rankings.ts）。
 * queryKey=['benchmarks','ranking',filters]；staleTime 5min；
 * placeholderData: keepPreviousData（切筛选 non-blocking 保留旧数据）。
 * INT-730 接线：真实端点经 client.ts，失败抛 ApiError → 错误态（旧 Vue 同款「排行加载失败 + 重试」）。
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
        subjectName: filters.subjectName || undefined,
      })
      return (data?.items ?? []).map(mapRankingRowDto)
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
    errorMessage: query.error instanceof Error ? query.error.message : null,
    refetch: () => void query.refetch(),
  }
}

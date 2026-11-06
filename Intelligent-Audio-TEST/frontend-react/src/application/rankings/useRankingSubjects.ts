/**
 * 主体联想查询（application 层，防抖 300ms，enabled=有输入）。
 * GET /benchmarks/ranking/subjects?suite=（benchmark:ranking:read）；
 * 后端返回被测主体纯字符串数组，直达 Domain string[]（无 snake_case 字段可转换，
 * 不经 adapter——14_benchmark排行.md §9）；联想加载失败静默不打断输入。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchBenchmarkRankingSubjects } from '@/infrastructure/api/benchmarkApi'

export interface RankingSubjectsResult {
  subjects: string[]
  isLoading: boolean
}

export function useRankingSubjects(suite: string, enabled: boolean): RankingSubjectsResult {
  const query = useQuery({
    queryKey: ['benchmarks', 'ranking', 'subjects', suite],
    queryFn: async () => {
      const data = await fetchBenchmarkRankingSubjects(suite || undefined)
      return data?.items ?? []
    },
    staleTime: 5 * 60_000,
    enabled,
    // 联想加载失败静默：不报错 toast、不打断输入
    retry: false,
  })

  return {
    subjects: query.data ?? [],
    isLoading: query.isLoading,
  }
}

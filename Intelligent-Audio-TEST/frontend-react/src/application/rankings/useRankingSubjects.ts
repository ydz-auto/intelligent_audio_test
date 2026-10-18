/**
 * 主体联想查询（application 层，防抖 300ms，enabled=有输入）。
 * GET /benchmarks/ranking/subjects?suite=（benchmark:ranking:read）；
 * 联想加载失败静默不打断输入（14_benchmark排行.md §4.3/§7）。
 * INT-730 接线：真实端点返回 string[]，mapRankingSubjectDto 直透。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchBenchmarkRankingSubjects } from '@/infrastructure/api/benchmarkApi'
import { mapRankingSubjectDto } from '@/infrastructure/adapters/benchmarkAdapter'

export interface RankingSubjectsResult {
  subjects: string[]
  isLoading: boolean
}

export function useRankingSubjects(suite: string, enabled: boolean): RankingSubjectsResult {
  const query = useQuery({
    queryKey: ['benchmarks', 'ranking', 'subjects', suite],
    queryFn: async () => {
      const data = await fetchBenchmarkRankingSubjects(suite || undefined)
      return (data?.items ?? []).map(mapRankingSubjectDto)
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

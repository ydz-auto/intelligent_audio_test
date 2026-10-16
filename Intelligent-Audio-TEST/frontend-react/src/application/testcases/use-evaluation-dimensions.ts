/**
 * 评估维度 query（application 层，11_用例域.md §3.4 评估维度 facet）。
 * queryKey ['evaluation','dimensions','options']；维度增删后同 queryKey 失效刷新。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchDimensionOptions } from '@/infrastructure/api/evaluation-api'

export function useDimensionOptions(algorithmType?: string | null) {
  return useQuery({
    queryKey: ['evaluation', 'dimensions', 'options', algorithmType ?? 'all'],
    queryFn: () => fetchDimensionOptions(algorithmType ?? undefined),
    staleTime: 30_000,
  })
}

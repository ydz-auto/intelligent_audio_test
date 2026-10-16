/**
 * 排行重算 mutation（application 层）。POST /api/v1/benchmarks/ranking/compute
 * （benchmark:ranking:compute）。成功 toast + 失效 rankings 查询缓存自动刷新；
 * 失败 toast 需传达「上一次排行结果仍可查看」（后端失败语义：整体失败不触碰 ReadModel）。
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { computeBenchmarkRanking } from '@/infrastructure/api/benchmarkApi'

export function useComputeRanking() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (params: { suite?: string; category?: string; source?: string }) => {
      const result = await computeBenchmarkRanking(params)
      if (!result.success) {
        throw new Error(result.message || '排行计算失败')
      }
      return result
    },
    onSuccess: () => {
      toast.success('排行计算完成')
      void queryClient.invalidateQueries({ queryKey: ['benchmarks', 'ranking'] })
    },
    onError: (error: Error) => {
      toast.error(`${error.message}，上一次排行结果仍可查看`)
    },
  })
}

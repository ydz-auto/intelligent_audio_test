/**
 * 排行重算 mutation（application 层）。POST /api/v1/benchmarks/ranking/compute
 * （benchmark:ranking:compute）。成功 toast + 失效 rankings 查询缓存自动刷新；
 * 失败 toast 需传达「上一次排行结果仍可查看」（后端失败语义：整体失败不触碰 ReadModel；
 * client 已把业务失败收敛为 ApiError，此处统一兜中文 userMessage）。
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { computeBenchmarkRanking } from '@/infrastructure/api/benchmarkApi'

export function useComputeRanking() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (params: { suite?: string; category?: string; source?: string }) => {
      await computeBenchmarkRanking(params)
      return true
    },
    onSuccess: () => {
      toast.success('排行计算完成')
      void queryClient.invalidateQueries({ queryKey: ['benchmarks', 'ranking'] })
    },
    onError: (error: Error) => {
      const message =
        (error as { userMessage?: string }).userMessage || error.message
      toast.error(`${message}，上一次排行结果仍可查看`)
    },
  })
}

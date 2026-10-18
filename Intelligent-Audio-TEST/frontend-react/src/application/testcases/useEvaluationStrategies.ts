/**
 * 评估策略 query/mutations（application 层，11_用例域.md §5.1.3 评估策略节）。
 * queryKey ['evaluation','strategies']；新建策略入库后失效刷新（Select 选项即时含新策略，
 * 全局可复用——跨组件状态同步点③）。
 * 依赖主项目 INT-590【后端】策略卡；mock 阶段用前端结构（evaluationStrategiesApi）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  createEvaluationStrategy,
  fetchEvaluationStrategies,
} from '@/infrastructure/api/evaluationStrategiesApi'

export const EVALUATION_STRATEGIES_KEY = ['evaluation', 'strategies'] as const

export function useEvaluationStrategies() {
  return useQuery({
    queryKey: EVALUATION_STRATEGIES_KEY,
    queryFn: fetchEvaluationStrategies,
    staleTime: 30_000,
  })
}

export function useCreateEvaluationStrategy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createEvaluationStrategy,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: EVALUATION_STRATEGIES_KEY })
    },
  })
}

/**
 * 测试执行算法选项（application 层；10_测试执行.md §3.3；INT-646 返修）。
 * 接真实 GET /algorithm/options（与评测域 fetchAlgorithmOptions 同端点），
 * 供 useAlgorithmChannel（步骤一算法联动）与 API 编辑弹窗（关联算法下拉）共用。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchTestAlgorithmOptions } from '@/infrastructure/api/test-execution-api'

export function useTestAlgorithmOptions() {
  return useQuery({
    queryKey: ['test-execution', 'algorithm-options'],
    queryFn: fetchTestAlgorithmOptions,
    staleTime: 5 * 60_000,
  })
}

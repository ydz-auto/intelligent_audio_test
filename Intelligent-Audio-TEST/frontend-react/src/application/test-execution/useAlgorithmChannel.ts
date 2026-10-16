/**
 * 全局算法通道（application 层；10_测试执行.md §3.3 本卡关键裁定）。
 * 挂载读全局 store——非空时预选；页内选择即写回 setAlgorithmId（Toast
 * 「已切换全局算法为 {名}」）；页内不提供「取消选择」（清空唯一入口=导航栏切换器）。
 * 步骤一/二列表过滤自动附 algorithm_type（toReportAlgorithmType 映射，与报告域同源）。
 */
import { useCallback, useMemo } from 'react'
import { toast } from 'sonner'

import { toReportAlgorithmType } from '@/features/reports/lib/algorithm'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import {
  MOCK_TEST_ALGORITHMS,
  type TestAlgorithmOption,
} from '@/infrastructure/mock/test-execution-mock'

export function useAlgorithmChannel() {
  const algorithmId = useAlgorithmStore((s) => s.algorithmId)
  const setAlgorithmId = useAlgorithmStore((s) => s.setAlgorithmId)

  /** 当前算法对象（含 enabled 过滤；全局 store 值不在选项内时回退 undefined） */
  const current = useMemo<TestAlgorithmOption | undefined>(
    () => MOCK_TEST_ALGORITHMS.find((a) => a.id === algorithmId && a.enabled),
    [algorithmId]
  )

  /** 已启用算法选项（仅在线 options，照 §3.4） */
  const enabledOptions = useMemo(
    () => MOCK_TEST_ALGORITHMS.filter((a) => a.enabled),
    []
  )

  /** 页面内选择即写回全局 store（双向同步契约） */
  const selectAlgorithm = useCallback(
    (id: string) => {
      setAlgorithmId(id)
      const option = MOCK_TEST_ALGORITHMS.find((a) => a.id === id)
      if (option) toast.success(`已切换全局算法为 ${option.name}`)
    },
    [setAlgorithmId]
  )

  /** 列表过滤用 algorithm_type（无映射返回 undefined → 不筛选） */
  const algorithmType = useMemo(() => toReportAlgorithmType(algorithmId), [algorithmId])

  return {
    algorithmId,
    current,
    enabledOptions,
    selectAlgorithm,
    algorithmType,
  }
}

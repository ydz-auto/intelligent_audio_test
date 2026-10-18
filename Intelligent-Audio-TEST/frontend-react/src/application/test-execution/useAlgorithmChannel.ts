/**
 * 全局算法通道（application 层；10_测试执行.md §3.3 本卡关键裁定）。
 * 挂载读全局 store——非空时预选；页内选择即写回 setAlgorithmId（Toast
 * 「已切换全局算法为 {名}」）；页内不提供「取消选择」（清空唯一入口=导航栏切换器）。
 * 步骤一/二列表过滤自动附 algorithm_type（toReportAlgorithmType 映射，与报告域同源）。
 * 接线（INT-646 返修）：选项来自真实 GET /algorithm/options；全局算法不在真实选项内时
 * 视为「未选择」——chip 显示「未选择」且不附加算法过滤（避免把真实数据筛成空态，
 * 与 Vue 端「facet 未显式选择且全局算法无效时按全部展示」口径一致）。
 */
import { useCallback, useMemo } from 'react'
import { toast } from 'sonner'

import { toReportAlgorithmType } from '@/features/reports/lib/algorithm'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { useTestAlgorithmOptions } from '@/application/test-execution/useTestAlgorithmOptions'
import type { TestAlgorithmOption } from '@/domain/models/algorithm'

export function useAlgorithmChannel() {
  const algorithmId = useAlgorithmStore((s) => s.algorithmId)
  const setAlgorithmId = useAlgorithmStore((s) => s.setAlgorithmId)
  const optionsQuery = useTestAlgorithmOptions()
  const enabledOptions = useMemo<TestAlgorithmOption[]>(
    () => optionsQuery.data ?? [],
    [optionsQuery.data]
  )

  /** 当前算法对象（全局 store 值不在真实选项内时回退 undefined → chip 显示「未选择」） */
  const current = useMemo<TestAlgorithmOption | undefined>(
    () => enabledOptions.find((a) => a.id === algorithmId),
    [enabledOptions, algorithmId]
  )

  /** 页面内选择即写回全局 store（双向同步契约） */
  const selectAlgorithm = useCallback(
    (id: string) => {
      setAlgorithmId(id)
      const option = enabledOptions.find((a) => a.id === id)
      if (option) toast.success(`已切换全局算法为 ${option.name}`)
    },
    [enabledOptions, setAlgorithmId]
  )

  /** 列表过滤用 algorithm_type：仅当全局算法存在于真实选项内时取值，否则 undefined（不筛选） */
  const algorithmType = useMemo(
    () => (current ? toReportAlgorithmType(algorithmId) : undefined),
    [current, algorithmId]
  )

  return {
    algorithmId,
    current,
    enabledOptions,
    selectAlgorithm,
    algorithmType,
  }
}

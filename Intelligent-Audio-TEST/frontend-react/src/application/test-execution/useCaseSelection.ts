/**
 * 用例选择编排（application 层；10_测试执行.md §3.5）。
 * 正选/反选：POST /testcases/ids 按当前筛选条件圈定全量 ID（现 fetchCaseIdsByFilter
 * 口径平移）；反选=全量集−当前选中集（对称差）；0 选中时等价全选结果。
 * 汇总口径：已选 n 条 · 手动勾选 a · 反选补齐 b；未手动选择时按筛选条件使用全部 total。
 */
import { useMemo } from 'react'
import { toast } from 'sonner'

import { fetchCaseIdsByFilter } from '@/infrastructure/api/testcases-ids-api'
import { useCaseSelectionStore } from '@/infrastructure/stores/case-selection-store'
import type { TestCase } from '@/domain/models/testCase'
import type { CaseSelectionFilter } from '@/domain/models/testExecution'

export function useCaseSelection(list: TestCase[]) {
  const manualCaseIds = useCaseSelectionStore((s) => s.manualCaseIds)
  const filterAllMode = useCaseSelectionStore((s) => s.filterAllMode)
  const invertAdded = useCaseSelectionStore((s) => s.invertAdded)
  const store = useCaseSelectionStore

  const selectedCount = manualCaseIds.length
  const allVisibleSelected = list.length > 0 && list.every((c) => manualCaseIds.includes(c.id))

  /** 全选结果（POST /testcases/ids 全量圈定） */
  const selectAllFiltered = async (filter: CaseSelectionFilter) => {
    const { ids, total } = await fetchCaseIdsByFilter(filter)
    store.getState().selectMany(ids)
    toast.success(`已全选 ${total} 条用例`)
  }

  /** 反选（对称差） */
  const invertSelection = async (filter: CaseSelectionFilter) => {
    const { ids } = await fetchCaseIdsByFilter(filter)
    store.getState().invertWith(ids)
    const invertedCount = ids.length - manualCaseIds.length
    if (invertedCount > 0) toast.success(`已反选，补齐 ${invertedCount} 条用例`)
  }

  const clearSelection = () => store.getState().clearSelection()

  const toggleCase = (id: string) => store.getState().toggleCase(id)

  /**
   * 列表头「全选用例」（INT-1970）：与「全选结果」同口径——始终按当前筛选条件经
   * POST /testcases/ids 取全量 ID（不按已加载分页圈定）；取消勾选时移除同一全量集合。
   * 勾选态由调用方按「筛选总数」判定（selectedCount >= total），不在本函数内推断。
   */
  const toggleAllFiltered = async (filter: CaseSelectionFilter, checked: boolean) => {
    const { ids, total } = await fetchCaseIdsByFilter(filter)
    if (checked) {
      store.getState().selectMany(ids)
      toast.success(`已全选 ${total} 条用例`)
      return
    }
    store.getState().removeMany(ids)
  }

  /** 汇总口径：手动勾选 a · 反选补齐 b */
  const summary = useMemo(
    () => ({
      selected: selectedCount,
      manual: manualCaseIds.length,
      invertAdded: invertAdded.length,
    }),
    [manualCaseIds, invertAdded, selectedCount]
  )

  return {
    manualCaseIds,
    filterAllMode,
    selectedCount,
    allVisibleSelected,
    summary,
    toggleCase,
    toggleAllFiltered,
    selectAllFiltered,
    invertSelection,
    clearSelection,
  }
}

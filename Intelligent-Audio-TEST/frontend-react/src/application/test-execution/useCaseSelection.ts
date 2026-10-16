/**
 * 用例选择编排（application 层；10_测试执行.md §3.5）。
 * 正选/反选：POST /testcases/ids 按当前筛选条件圈定全量 ID（现 fetchCaseIdsByFilter
 * 口径平移）；反选=全量集−当前选中集（对称差）；0 选中时等价全选结果。
 * 汇总口径：已选 n 条 · 手动勾选 a · 反选补齐 b；未手动选择时按筛选条件使用全部 total。
 */
import { useMemo } from 'react'
import { toast } from 'sonner'

import { fetchCaseIdsByFilter } from '@/infrastructure/api/test-execution-api'
import { useCaseSelectionStore } from '@/infrastructure/stores/case-selection-store'
import type { TestCase } from '@/domain/models/testCase'
import type { TestCaseFilter } from '@/infrastructure/api/test-execution-api'

export function useCaseSelection(list: TestCase[]) {
  const manualCaseIds = useCaseSelectionStore((s) => s.manualCaseIds)
  const filterAllMode = useCaseSelectionStore((s) => s.filterAllMode)
  const invertAdded = useCaseSelectionStore((s) => s.invertAdded)
  const store = useCaseSelectionStore

  const selectedCount = manualCaseIds.length
  const allVisibleSelected = list.length > 0 && list.every((c) => manualCaseIds.includes(c.id))

  /** 全选结果（POST /testcases/ids 全量圈定） */
  const selectAllFiltered = async (filter: TestCaseFilter) => {
    const { ids, total } = await fetchCaseIdsByFilter(filter)
    store.getState().selectMany(ids)
    toast.success(`已全选 ${total} 条用例`)
  }

  /** 反选（对称差） */
  const invertSelection = async (filter: TestCaseFilter) => {
    const { ids } = await fetchCaseIdsByFilter(filter)
    store.getState().invertWith(ids)
    const invertedCount = ids.length - manualCaseIds.length
    if (invertedCount > 0) toast.success(`已反选，补齐 ${invertedCount} 条用例`)
  }

  const clearSelection = () => store.getState().clearSelection()

  const toggleCase = (id: string) => store.getState().toggleCase(id)

  /** 表头全选=正选当前页（勾选态点按=取消当前页勾选） */
  const toggleAllVisible = () => {
    const visibleIds = new Set(list.map((c) => c.id))
    if (allVisibleSelected) {
      store.getState().selectMany(manualCaseIds.filter((id) => !visibleIds.has(id)))
    } else {
      store.getState().selectMany(list.map((c) => c.id))
    }
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
    toggleAllVisible,
    selectAllFiltered,
    invertSelection,
    clearSelection,
  }
}

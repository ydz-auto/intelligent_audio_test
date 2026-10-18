/**
 * 已选用例集 store（infrastructure/stores 层；10_测试执行.md §4）。
 * 手动勾选集 + 圈定模式（manual/filter-all）；内存态，刷新回到步骤一重选
 * （用例集属敏感流程态，不进 URL 防超长）。
 */
import { create } from 'zustand'

type CaseSelectionState = {
  /** 手动勾选（含全选结果/反选落点）的用例 id 集 */
  manualCaseIds: string[]
  /** 圈定模式：filter-all = 未手动选择时按当前筛选条件使用全部 */
  filterAllMode: boolean
  /** 反选补齐：手动勾选 a 条 · 反选补齐 b 条（汇总行口径透明） */
  invertAdded: string[]
  toggleCase: (id: string) => void
  /** 正选当前页/全量圈定（POST /testcases/ids 全量 id 集落点） */
  selectMany: (ids: string[]) => void
  /** 取消勾选一组 id（分组/标签卡「本组取消全选」；INT-710） */
  removeMany: (ids: string[]) => void
  /** 反选：选中集 = 全量集 − 当前选中集（对称差） */
  invertWith: (allIds: string[]) => void
  clearSelection: () => void
  /** 进入步骤三时把「全量圈定模式」转为显性选中集（口径落定） */
  materializeAll: (allIds: string[]) => void
}

export const useCaseSelectionStore = create<CaseSelectionState>((set) => ({
  manualCaseIds: [],
  filterAllMode: true,
  invertAdded: [],

  toggleCase: (id) =>
    set((s) => ({
      manualCaseIds: s.manualCaseIds.includes(id)
        ? s.manualCaseIds.filter((x) => x !== id)
        : [...s.manualCaseIds, id],
      filterAllMode: false,
    })),

  selectMany: (ids) =>
    set((s) => {
      const merged = Array.from(new Set([...s.manualCaseIds, ...ids]))
      return { manualCaseIds: merged, filterAllMode: false }
    }),

  removeMany: (ids) =>
    set((s) => {
      const remove = new Set(ids)
      const kept = s.manualCaseIds.filter((id) => !remove.has(id))
      return {
        manualCaseIds: kept,
        invertAdded: s.invertAdded.filter((id) => !remove.has(id)),
        filterAllMode: false,
      }
    }),

  invertWith: (allIds) =>
    set((s) => {
      const current = new Set(s.manualCaseIds)
      const inverted = allIds.filter((id) => !current.has(id))
      return {
        manualCaseIds: inverted,
        invertAdded: inverted.filter((id) => !current.has(id)),
        filterAllMode: false,
      }
    }),

  clearSelection: () =>
    set({ manualCaseIds: [], invertAdded: [], filterAllMode: true }),

  materializeAll: (allIds) =>
    set({ manualCaseIds: allIds, invertAdded: [], filterAllMode: false }),
}))

/**
 * 已选用例集 store（infrastructure/stores 层；10_测试执行.md §4）。
 * 手动勾选集 + 圈定模式（manual/filter-all）；内存态，刷新回到步骤一重选
 * （用例集属敏感流程态，不进 URL 防超长）。
 */
import { create } from 'zustand'
import type { CaseSelectionFilter } from '@/domain/models/testExecution'

type CaseSelectionState = {
  /** 手动勾选（含全选结果/反选落点）的用例 id 集 */
  manualCaseIds: string[]
  /** 圈定模式：filter-all = 未手动选择时按当前筛选条件使用全部 */
  filterAllMode: boolean
  /** 反选补齐：手动勾选 a 条 · 反选补齐 b 条（汇总行口径透明） */
  invertAdded: string[]
  /**
   * 当前筛选条件（关键字/分组名/标签/评估维度/算法）。INT-646 代码审计 P2 要求
   * filter-all 圈定按该筛选而非仅算法维度；INT-1544 由 StepCases 随页面筛选持续
   * 同步（组件卸载后仍保留到启动），launch 时随启动流程传入 createTask。
   */
  filter: CaseSelectionFilter
  /** 当前筛选条件下的用例总数（步骤一列表 total，随筛选同步；启动弹窗摘要按此显数） */
  filterAllTotal: number
  setFilter: (filter: CaseSelectionFilter, filteredTotal?: number) => void
  toggleCase: (id: string) => void
  /** 正选当前页/全量圈定（POST /testcases/ids 全量 id 集落点） */
  selectMany: (ids: string[]) => void
  /** 取消勾选一组 id（分组/标签卡「本组取消全选」；INT-710） */
  removeMany: (ids: string[]) => void
  /**
   * 移除一组 id 但保留圈定模式（INT-1138：行内删除/恢复/彻底删除、删除分组后同步移出
   * 勾选集——不改变 filterAllMode，避免「按筛选使用全部」语义被静默切换）
   */
  removeSelected: (ids: string[]) => void
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
  filter: {},
  filterAllTotal: 0,
  setFilter: (filter, filteredTotal) =>
    set((s) => ({
      filter,
      filterAllTotal: filteredTotal ?? s.filterAllTotal,
    })),

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

  removeSelected: (ids) =>
    set((s) => {
      const remove = new Set(ids)
      return {
        manualCaseIds: s.manualCaseIds.filter((id) => !remove.has(id)),
        invertAdded: s.invertAdded.filter((id) => !remove.has(id)),
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
    // INT-1544：只清选择态，不清筛选条件——筛选是步骤一页面态，由 StepCases 同步维护；
    // 在「清空选择」里一并清掉会让界面仍是「全部 1 条」而 filter-all 圈定回退全库
    set({ manualCaseIds: [], invertAdded: [], filterAllMode: true }),

  materializeAll: (allIds) =>
    set({ manualCaseIds: allIds, invertAdded: [], filterAllMode: false }),
}))

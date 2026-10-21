/**
 * 已选资源集 store（infrastructure/stores 层；10_测试执行.md §4）。
 * E2E=设备 id 集 / API=API id 集；算法过滤临时解除态（「查看全部」仅本页生效）内存持有。
 * INT-1119（2026-10-21）：新增 `selectionOrder` 统一选中顺序——勾选追加到末尾、取消移除、
 * 全选按展示顺序批量追加、清空置空；device_ids/api_ids 载荷与 target_modes 均由该列表
 * 派生（同源，§3.6.5）。取消选择时同步删除 execution store 的目标模式项（回默认并行）。
 */
import { create } from 'zustand'

import type { TargetType } from '@/domain/models/testExecution'
import { useExecutionStore } from '@/infrastructure/stores/execution-store'

/** 统一选中顺序条目（§3.6.5：target_modes 列表顺序 = 选中顺序 = 串行链顺序） */
export interface SelectionEntry {
  targetType: TargetType
  targetId: number
}

type ResourceSelectionState = {
  deviceIds: number[]
  apiIds: number[]
  /** 统一选中顺序（勾选追加/取消移除/全选按展示顺序批量追加/清空置空；§3.6.5） */
  selectionOrder: SelectionEntry[]
  /** 临时解除算法过滤（「查看全部」仅本页生效，Alert info 提示全局算法仍为原值） */
  temporaryShowAll: boolean
  toggleDevice: (id: number) => void
  toggleApi: (id: number) => void
  selectAllDevices: (ids: number[]) => void
  selectAllApis: (ids: number[]) => void
  removeDevice: (id: number) => void
  removeApi: (id: number) => void
  clearResources: () => void
  setTemporaryShowAll: (value: boolean) => void
}

/** 从选中顺序移除某目标（取消选择即清 execution store 模式项，回默认并行） */
function removeOrderEntry(order: SelectionEntry[], targetType: TargetType, targetId: number): SelectionEntry[] {
  const next = order.filter(
    (entry) => entry.targetType !== targetType || entry.targetId !== targetId
  )
  return next
}

export const useResourceSelectionStore = create<ResourceSelectionState>((set) => ({
  deviceIds: [],
  apiIds: [],
  selectionOrder: [],
  temporaryShowAll: false,

  toggleDevice: (id) =>
    set((s) => {
      const isSelected = s.deviceIds.includes(id)
      const nextDeviceIds = isSelected
        ? s.deviceIds.filter((x) => x !== id)
        : [...s.deviceIds, id]
      const nextOrder = isSelected
        ? removeOrderEntry(s.selectionOrder, 'device', id)
        : [...s.selectionOrder, { targetType: 'device' as const, targetId: id }]
      if (isSelected) useExecutionStore.getState().removeTargetMode('device', id)
      return { deviceIds: nextDeviceIds, selectionOrder: nextOrder }
    }),

  toggleApi: (id) =>
    set((s) => {
      const isSelected = s.apiIds.includes(id)
      const nextApiIds = isSelected
        ? s.apiIds.filter((x) => x !== id)
        : [...s.apiIds, id]
      const nextOrder = isSelected
        ? removeOrderEntry(s.selectionOrder, 'api', id)
        : [...s.selectionOrder, { targetType: 'api' as const, targetId: id }]
      if (isSelected) useExecutionStore.getState().removeTargetMode('api', id)
      return { apiIds: nextApiIds, selectionOrder: nextOrder }
    }),

  selectAllDevices: (ids) =>
    set((s) => {
      // 先移除全部设备条目，再按展示顺序批量追加（id 集即全选结果）
      const orderWithoutDevices = s.selectionOrder.filter((entry) => entry.targetType !== 'device')
      const newlyOrdered = ids.map((id) => ({ targetType: 'device' as const, targetId: id }))
      // 取消勾选的目标清模式项
      const removed = s.deviceIds.filter((x) => !ids.includes(x))
      removed.forEach((x) => useExecutionStore.getState().removeTargetMode('device', x))
      return { deviceIds: ids, selectionOrder: [...orderWithoutDevices, ...newlyOrdered] }
    }),

  selectAllApis: (ids) =>
    set((s) => {
      const orderWithoutApis = s.selectionOrder.filter((entry) => entry.targetType !== 'api')
      const newlyOrdered = ids.map((id) => ({ targetType: 'api' as const, targetId: id }))
      const removed = s.apiIds.filter((x) => !ids.includes(x))
      removed.forEach((x) => useExecutionStore.getState().removeTargetMode('api', x))
      return { apiIds: ids, selectionOrder: [...orderWithoutApis, ...newlyOrdered] }
    }),

  removeDevice: (id) =>
    set((s) => {
      useExecutionStore.getState().removeTargetMode('device', id)
      return {
        deviceIds: s.deviceIds.filter((x) => x !== id),
        selectionOrder: removeOrderEntry(s.selectionOrder, 'device', id),
      }
    }),

  removeApi: (id) =>
    set((s) => {
      useExecutionStore.getState().removeTargetMode('api', id)
      return {
        apiIds: s.apiIds.filter((x) => x !== id),
        selectionOrder: removeOrderEntry(s.selectionOrder, 'api', id),
      }
    }),

  clearResources: () => {
    // 清空选择时同步清空执行模式项（§3.6.5）
    useExecutionStore.getState().resetTargetModes()
    set({ deviceIds: [], apiIds: [], selectionOrder: [] })
  },

  setTemporaryShowAll: (value) => set({ temporaryShowAll: value }),
}))

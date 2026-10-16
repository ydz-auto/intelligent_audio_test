/**
 * 已选资源集 store（infrastructure/stores 层；10_测试执行.md §4）。
 * E2E=设备 id 集 / API=API id 集；算法过滤临时解除态（「查看全部」仅本页生效）内存持有。
 */
import { create } from 'zustand'

type ResourceSelectionState = {
  deviceIds: number[]
  apiIds: number[]
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

export const useResourceSelectionStore = create<ResourceSelectionState>((set) => ({
  deviceIds: [],
  apiIds: [],
  temporaryShowAll: false,

  toggleDevice: (id) =>
    set((s) => ({
      deviceIds: s.deviceIds.includes(id)
        ? s.deviceIds.filter((x) => x !== id)
        : [...s.deviceIds, id],
    })),

  toggleApi: (id) =>
    set((s) => ({
      apiIds: s.apiIds.includes(id) ? s.apiIds.filter((x) => x !== id) : [...s.apiIds, id],
    })),

  selectAllDevices: (ids) => set({ deviceIds: ids }),
  selectAllApis: (ids) => set({ apiIds: ids }),

  removeDevice: (id) =>
    set((s) => ({ deviceIds: s.deviceIds.filter((x) => x !== id) })),
  removeApi: (id) => set((s) => ({ apiIds: s.apiIds.filter((x) => x !== id) })),

  clearResources: () => set({ deviceIds: [], apiIds: [] }),
  setTemporaryShowAll: (value) => set({ temporaryShowAll: value }),
}))

/**
 * 挑选合并购物车 store（application/tasks/cherry-pick，18_挑选合并交互重设计.md §7.2/§6.3，INT-600）。
 * Zustand 单例：购物车镜像（groups/total/invalidItemIds）+ resultIdSet + revision。
 * 服务端为准、本地为镜像；任何写操作后 refreshCart() 拉服务端全量回写（防漂移）。
 * 全局购物车角标计数源（INT-344 导航栏入口消费同一 store）。
 */
import { create } from 'zustand'

import {
  addToCart,
  clearCart as apiClearCart,
  deletePickSet as apiDeletePickSet,
  fetchCart,
  fetchPickSets,
  removeCartItems,
  restorePickSet as apiRestorePickSet,
  savePickSet as apiSavePickSet,
} from '@/infrastructure/api/cherry-pick-api'
import type { PickCartGroup, PickSet } from '@/domain/models/cherryPick'

export interface AddToCartResult {
  addedCount: number
  skippedCount: number
  invalidCount: number
}

type PickCartState = {
  /** 购物车镜像（按来源任务分组） */
  groups: PickCartGroup[]
  /** 角标/汇总用：条目总数 */
  total: number
  /** 失效条目 id 集（源结果已删除，下单跳过 + 一键移除） */
  invalidItemIds: string[]
  /** R10 已加购标记数据源（result_id 集，挑选树/购物车共用） */
  resultIdSet: Set<number>
  /** 购物车 revision（增删后自增；预览摘要 queryKey 失效用） */
  revision: number
  /** 挑选集 */
  pickSets: PickSet[]
  /** 初始化/同步中 */
  loading: boolean

  /** 拉服务端全量回写镜像 */
  refreshCart: () => Promise<void>
  /** 加购（按 result_id；重复幂等跳过 uq_cherry_cart_user_result） */
  addEntries: (resultIds: number[]) => Promise<AddToCartResult>
  /** 移除（单条/节点/整组/批量 item_ids 数组） */
  removeEntries: (itemIds: string[]) => Promise<void>
  /** 一键移除失效 */
  removeInvalid: () => Promise<void>
  /** 清空购物车 */
  clearCart: () => Promise<void>
  /** 另存为挑选集 */
  saveAsPickSet: (name: string) => Promise<PickSet | null>
  /** 恢复挑选集进购物车 */
  restorePickSet: (setId: string) => Promise<number>
  /** 删除挑选集 */
  deletePickSet: (setId: string) => Promise<void>
  /** 刷新挑选集列表 */
  refreshPickSets: () => Promise<void>
}

function syncFromGroups(groups: PickCartGroup[]) {
  const entries = groups.flatMap((g) => g.entries)
  return {
    groups,
    total: entries.length,
    invalidItemIds: entries.filter((e) => e.invalid).map((e) => e.itemId),
    resultIdSet: new Set(entries.map((e) => e.resultId)),
  }
}

export const usePickCartStore = create<PickCartState>((set, get) => ({
  groups: [],
  total: 0,
  invalidItemIds: [],
  resultIdSet: new Set(),
  revision: 0,
  pickSets: [],
  loading: true,

  refreshCart: async () => {
    const groups = await fetchCart()
    set({ ...syncFromGroups(groups), loading: false, revision: get().revision + 1 })
  },

  addEntries: async (resultIds) => {
    const { addedCount, skippedCount, invalidCount } = await addToCart(resultIds)
    set({ revision: get().revision + 1 })
    await get().refreshCart()
    return { addedCount, skippedCount, invalidCount }
  },

  removeEntries: async (itemIds) => {
    if (itemIds.length === 0) return
    await removeCartItems(itemIds)
    set({ revision: get().revision + 1 })
    await get().refreshCart()
  },

  removeInvalid: async () => {
    const ids = get().invalidItemIds
    if (ids.length === 0) return
    await removeCartItems(ids)
    set({ revision: get().revision + 1 })
    await get().refreshCart()
  },

  clearCart: async () => {
    await apiClearCart()
    set({ revision: get().revision + 1 })
    await get().refreshCart()
  },

  saveAsPickSet: async (name) => {
    const setEntry = await apiSavePickSet(name)
    await get().refreshPickSets()
    return setEntry
  },

  restorePickSet: async (setId) => {
    const { restored } = await apiRestorePickSet(setId)
    set({ revision: get().revision + 1 })
    await get().refreshCart()
    return restored
  },

  deletePickSet: async (setId) => {
    await apiDeletePickSet(setId)
    await get().refreshPickSets()
  },

  refreshPickSets: async () => {
    const pickSets = await fetchPickSets()
    set({ pickSets })
  },
}))

/** 初始化入口（CherryPickTab/向导挂载时调用一次） */
export async function initPickCartStore() {
  const store = usePickCartStore.getState()
  await Promise.all([store.refreshCart(), store.refreshPickSets()])
}

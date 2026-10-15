/**
 * 挑选合并购物车 store（application 层，09_任务域.md §5.14b）。
 * 全局角标计数源（INT-344 导航栏入口消费）；mock 态内存 store，接线后持久化可选。
 * 文案红线：站内一律「挑选合并/挑选/加入购物车/购物车/下单/挑选集」。
 */
import { create } from 'zustand'

import type { CartEntry, PickSet } from '@/domain/models/task'

type CartState = {
  /** 购物车条目（按来源任务分组展示，条目自带 sourceTaskId/Name） */
  entries: CartEntry[]
  /** 挑选集（另存为挑选集，可恢复进购物车/删除） */
  pickSets: PickSet[]
  addEntries: (entries: CartEntry[]) => void
  removeEntry: (entryId: string) => void
  removeGroup: (sourceTaskId: number) => void
  clearCart: () => void
  saveAsPickSet: (name: string) => void
  restorePickSet: (setId: string) => void
  deletePickSet: (setId: string) => void
}

let entrySeq = 0

export const useCartStore = create<CartState>((set) => ({
  entries: [
    {
      id: `cart-${entrySeq++}`,
      sourceTaskId: 1042,
      sourceTaskName: '智能音箱旗舰机型全量回归 · 第 3 轮',
      caseName: '远场 3m 唤醒词响应',
      deviceName: '音箱-客厅位',
      executionStatus: 'completed',
      evaluationStatus: 'completed',
    },
    {
      id: `cart-${entrySeq++}`,
      sourceTaskId: 1042,
      sourceTaskName: '智能音箱旗舰机型全量回归 · 第 3 轮',
      caseName: '噪声环境 5m 唤醒（电视声）',
      deviceName: '音箱-卧室位',
      executionStatus: 'failed',
      evaluationStatus: 'failed',
    },
    {
      id: `cart-${entrySeq++}`,
      sourceTaskId: 1041,
      sourceTaskName: '车载语音助手唤醒词响应测试',
      caseName: '车载 1m 唤醒词响应',
      deviceName: '车载屏-主驾位',
      executionStatus: 'completed',
      evaluationStatus: 'completed',
    },
  ],
  pickSets: [
    {
      id: 'set-1',
      name: '远场高置信度候选集',
      createdAt: '2026-10-14T10:00:00',
      entries: [
        {
          id: 'set-1-a',
          sourceTaskId: 1042,
          sourceTaskName: '智能音箱旗舰机型全量回归 · 第 3 轮',
          caseName: '近场 1m 唤醒词响应',
          deviceName: '音箱-客厅位',
          executionStatus: 'completed',
          evaluationStatus: 'completed',
        },
      ],
    },
  ],
  addEntries: (entries) => set((s) => ({ entries: [...s.entries, ...entries] })),
  removeEntry: (entryId) =>
    set((s) => ({ entries: s.entries.filter((e) => e.id !== entryId) })),
  removeGroup: (sourceTaskId) =>
    set((s) => ({
      entries: s.entries.filter((e) => e.sourceTaskId !== sourceTaskId),
    })),
  clearCart: () => set({ entries: [] }),
  saveAsPickSet: (name) =>
    set((s) => ({
      pickSets: [
        ...s.pickSets,
        { id: `set-${Date.now()}`, name, createdAt: new Date().toISOString(), entries: s.entries },
      ],
    })),
  restorePickSet: (setId) =>
    set((s) => {
      const pick = s.pickSets.find((p) => p.id === setId)
      if (!pick) return s
      const existingIds = new Set(s.entries.map((e) => e.id))
      return {
        entries: [
          ...s.entries,
          ...pick.entries.filter((e) => !existingIds.has(e.id)),
        ],
      }
    }),
  deletePickSet: (setId) =>
    set((s) => ({ pickSets: s.pickSets.filter((p) => p.id !== setId) })),
}))

/**
 * 排行榜页「页内算法」store（infrastructure 层，INT-442 口径：公开页算法切换
 * 只过滤本页榜单、**不写回全局算法 store**——避免公开页污染全局）。
 * 形态：useRankingAlgorithmStore { algorithmType: string|null; setAlgorithm(type); clear() }，
 * 持久化 localStorage `iatp:rankings:v1:algorithm`；URL `algorithm=` 可还原（14_benchmark排行.md §3.2）。
 */
import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

type RankingAlgorithmState = {
  /** 页内当前算法 type；null = 「全部算法」（不按算法筛选） */
  algorithmType: string | null
  setAlgorithm: (algorithmType: string | null) => void
  clear: () => void
}

export const useRankingAlgorithmStore = create<RankingAlgorithmState>()(
  persist(
    (set) => ({
      algorithmType: null,
      setAlgorithm: (algorithmType) => set({ algorithmType }),
      clear: () => set({ algorithmType: null }),
    }),
    {
      name: 'iatp:rankings:v1:algorithm',
      storage: createJSONStorage(() => localStorage),
      // 页内 store 单字段，空值（null）也持久化以便 URL 还原对比
      partialize: (state) => ({ algorithmType: state.algorithmType }),
    }
  )
)

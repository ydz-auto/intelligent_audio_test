import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

/**
 * 全局算法切换 store（infrastructure 层，壳 INT-607 接线）。
 * 契约对齐 02_导航栏.md §3.4：algorithmType（string；空串=「全部算法」）+
 * setAlgorithm/clear；持久化 localStorage iatp:algorithm:v1。
 * 登出清空（clear）随登出流程执行（多账号切换不串值，§3.4 契约 6）。
 */

type AlgorithmState = {
  algorithmId: string
  setAlgorithmId: (algorithmId: string) => void
  /** 登出清空（多账号切换不串值；回「全部算法」态） */
  clear: () => void
}

export const useAlgorithmStore = create<AlgorithmState>()(
  persist(
    (set) => ({
      algorithmId: '',
      setAlgorithmId: (algorithmId) => set({ algorithmId }),
      clear: () => set({ algorithmId: '' }),
    }),
    {
      name: 'iatp:algorithm:v1',
      storage: createJSONStorage(() => localStorage),
    }
  )
)

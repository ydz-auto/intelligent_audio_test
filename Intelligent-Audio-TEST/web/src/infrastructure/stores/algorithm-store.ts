import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

/**
 * 全局算法切换 store（infrastructure 层）。
 * TODO(API 接线): 切换时联动业务列表页查询参数（后端按算法过滤）。
 */

type AlgorithmState = {
  algorithmId: string
  setAlgorithmId: (algorithmId: string) => void
}

export const useAlgorithmStore = create<AlgorithmState>()(
  persist(
    (set) => ({
      algorithmId: 'asr-v3',
      setAlgorithmId: (algorithmId) => set({ algorithmId }),
    }),
    {
      name: 'iatp:algorithm:v1',
      storage: createJSONStorage(() => localStorage),
    }
  )
)

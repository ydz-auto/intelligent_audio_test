import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

/**
 * 全局算法切换 store（infrastructure 层；INT-714 修正默认值）。
 * 默认 ''（未选择算法）——真实 /algorithm/options 仅含 voice_llm 一个算法，
 * mock 默认 'asr-v3' 会让列表请求自动附 algorithm_type=asr-v3 过滤掉全部真实用例/任务。
 */

type AlgorithmState = {
  algorithmId: string
  setAlgorithmId: (algorithmId: string) => void
}

export const useAlgorithmStore = create<AlgorithmState>()(
  persist(
    (set) => ({
      algorithmId: '',
      setAlgorithmId: (algorithmId) => set({ algorithmId }),
    }),
    {
      name: 'iatp:algorithm:v1',
      storage: createJSONStorage(() => localStorage),
    }
  )
)

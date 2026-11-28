import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

/**
 * 全局算法切换 store（infrastructure 层，壳 INT-607 接线）。
 * 契约对齐 02_导航栏.md §3.4：algorithmType（string；空串=「全部算法」）+
 * setAlgorithm/clear；持久化 localStorage iatp:algorithm:v1。
 * 上次选中算法按用户维度记录（lastUsedByUser）：登出只清当前值、不清历史，
 * 登录/会话恢复时 setActiveUser 回填该用户上次选择（多账号仍不串值）。
 */

type AlgorithmState = {
  algorithmId: string
  /** 当前会话用户 id（setAlgorithmId 据此记录 lastUsedByUser） */
  activeUserId: string
  /** 各用户上次选中的算法（登出保留，切换账号互不影响） */
  lastUsedByUser: Record<string, string>
  setAlgorithmId: (algorithmId: string) => void
  /** 登录/会话恢复后调用：回填该用户上次选中的算法（无历史则回「全部算法」） */
  setActiveUser: (userId: string) => void
  /** 登出清空当前值（多账号切换不串值），保留 lastUsedByUser 供下次登录恢复 */
  clear: () => void
}

export const useAlgorithmStore = create<AlgorithmState>()(
  persist(
    (set) => ({
      algorithmId: '',
      activeUserId: '',
      lastUsedByUser: {},
      setAlgorithmId: (algorithmId) =>
        set((s) => ({
          algorithmId,
          lastUsedByUser: s.activeUserId
            ? { ...(s.lastUsedByUser ?? {}), [s.activeUserId]: algorithmId }
            : (s.lastUsedByUser ?? {}),
        })),
      setActiveUser: (userId) =>
        set((s) => ({
          activeUserId: userId,
          // 同账号刷新保留当前值；换账号只用该账号自己的历史
          algorithmId:
            s.activeUserId === userId
              ? s.algorithmId || s.lastUsedByUser?.[userId] || ''
              : s.lastUsedByUser?.[userId] || '',
        })),
      clear: () => set({ algorithmId: '', activeUserId: '' }),
    }),
    {
      name: 'iatp:algorithm:v1',
      storage: createJSONStorage(() => localStorage),
    }
  )
)

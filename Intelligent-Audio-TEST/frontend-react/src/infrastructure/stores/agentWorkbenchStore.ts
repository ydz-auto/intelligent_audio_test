/**
 * 全局 Agent 工作台浮窗开关 store（infrastructure/stores 层；08_AI对话页.md §3.1B）。
 * useAgentWorkbench：{ open, minimized } + localStorage `iatp:agent-workbench:v1` 持久化——
 * 跨页面刷新/路由保持；open=true 时登录壳任意页面显示浮窗（§3.1B 全局驻留语义）。
 * 基座 §10 zustand 落位单文件单层（2026-10-17 前置审核打回修订：浮窗开关 store 收敛至此，
 * 删除 features/agent-workbench/use-agent-workbench.ts 与
 * application/agent-workbench/useAgentWorkbenchStore.ts 双落位）。
 */
import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

type AgentWorkbenchState = {
  open: boolean
  minimized: boolean
  setOpen: (open: boolean) => void
  setMinimized: (minimized: boolean) => void
  /** 魔法按钮开关：打开/关闭浮窗；打开时重置最小化态（§3.1B） */
  toggle: () => void
  /** 展开整页：关闭浮窗并导航 /ai-chat（§3.1B 浮窗头行动作；会话保留） */
  expandToFullPage: () => void
}

export const useAgentWorkbench = create<AgentWorkbenchState>()(
  persist(
    (set) => ({
      open: false,
      minimized: false,
      setOpen: (open) =>
        set((state) => ({
          open,
          minimized: open ? false : state.minimized,
        })),
      setMinimized: (minimized) => set({ minimized }),
      toggle: () =>
        set((state) => ({
          open: !state.open,
          minimized: !state.open ? false : state.minimized,
        })),
      expandToFullPage: () => set({ open: false, minimized: false }),
    }),
    {
      name: 'iatp:agent-workbench:v1',
      storage: createJSONStorage(() => localStorage),
    }
  )
)

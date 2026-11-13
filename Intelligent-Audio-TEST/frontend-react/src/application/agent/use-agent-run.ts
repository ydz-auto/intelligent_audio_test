/**
 * useAgentRun —— 平台 Agent run 状态的应用层入口（INT-2507 收敛为共享单一实例）。
 *
 * 状态与生命周期在 application/agent/agent-run-store 的模块级 store 里，整页（/ai-chat）
 * 与全局浮窗（AgentWorkbench）两个宿主订阅同一份：展开整页、刷新、同页双开都不再各持一套
 * sessionId / phase / 取消闸。本 hook 只做 React 绑定，并在宿主挂载时触发一次幂等恢复
 * （getAgentSession 校验会话 / 回填历史 / 收口刷新打断的气泡）。
 *
 * 原 `useAgentRun(handlers)` 的组件内状态与回调已移除：事件 → 消息补丁改由 store 唯一完成，
 * 宿主不再各自注册补丁器（那正是两条 run 重复写一份消息列表的来源）。
 */
import { useEffect } from 'react'

import {
  AGENT_RUN_PHASE,
  isAgentRunActive,
  useAgentRunStore,
  type AgentRunPhase,
} from '@/application/agent/agent-run-store'
import type { AgentRun } from '@/domain/models/agent'
import type { AgentStreamStatus } from '@/infrastructure/api/agentApi'

export { AGENT_RUN_PHASE, isAgentRunActive }
export type { AgentRunPhase }

export interface UseAgentRunResult {
  phase: AgentRunPhase
  run: AgentRun | null
  /** 事件流连接状态（reconnecting 时页面提示重连中） */
  streamStatus: AgentStreamStatus | null
  error: string | null
  /** 发起一轮对话（内部保证会话 + run + 订阅；失败落 error 态，不抛出） */
  send: (text: string, options?: { appendUserMessage?: boolean }) => Promise<void>
  /** 取消当前 run；成功返回 null，失败返回中文文案（同一 run 只发一次请求） */
  cancel: () => Promise<string | null>
  /** 复位（keepSession=true 保留会话上下文，仅清空本轮状态） */
  reset: (options?: { keepSession?: boolean }) => void
}

export function useAgentRun(): UseAgentRunResult {
  const phase = useAgentRunStore((state) => state.phase)
  const run = useAgentRunStore((state) => state.run)
  const streamStatus = useAgentRunStore((state) => state.streamStatus)
  const error = useAgentRunStore((state) => state.error)
  const send = useAgentRunStore((state) => state.send)
  const cancel = useAgentRunStore((state) => state.cancel)
  const reset = useAgentRunStore((state) => state.reset)

  // 宿主挂载恢复（幂等；浮窗展开整页 / 刷新都会走到这里，不打断进行中的 run）
  useEffect(() => {
    void useAgentRunStore.getState().restore()
  }, [])

  return { phase, run, streamStatus, error, send, cancel, reset }
}

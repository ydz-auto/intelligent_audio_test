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
 *
 * INT-2521 的「宿主卸载就取消在办 run」在单实例下会误伤另一宿主（浮窗展开整页 / 最小化都是
 * 卸载语义，但 run 本该继续），因此收窄为：宿主用 `useAgentRunHost` 登记存活，**只有最后一个
 * 宿主按取消语义离场**（浮窗「关闭」、离开 `/ai-chat` 路由）才取消；详见 store 的
 * `detachHost` / `AGENT_RUN_UNMOUNT_CANCEL_COPY`。
 */
import { useEffect, useRef } from 'react'

import {
  AGENT_RUN_PHASE,
  AGENT_RUN_UNMOUNT_CANCEL_COPY,
  isAgentRunActive,
  useAgentRunStore,
  type AgentRunHostDetachReason,
  type AgentRunHostKind,
  type AgentRunPhase,
} from '@/application/agent/agent-run-store'
import type { AgentRun } from '@/domain/models/agent'
import type { AgentStreamStatus } from '@/infrastructure/api/agentApi'

export { AGENT_RUN_PHASE, AGENT_RUN_UNMOUNT_CANCEL_COPY, isAgentRunActive }
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

/**
 * 宿主存活登记（INT-2521 按 INT-2507 A5–A7 收窄）：整页 `/ai-chat` 与浮窗各登记一次。
 *
 * - 浮窗「最小化」「展开整页」、整页 ↔ 浮窗切换都是暂时卸载：传 `'keep'`（默认），
 *   不取消在办 run —— 单实例下另一宿主仍会展示同一轮流式输出；
 * - 浮窗「关闭」由关闭按钮先 `detachAgentRunHost('workbench', 'cancel')` 声明意图；
 * - 整页卸载 = 离开 `/ai-chat` 路由：传 `'cancel'`。
 *
 * 只有「最后一个宿主按取消语义离场」才真正中止在办 run（两宿主同开时卸载一侧不误伤另一侧）。
 * 离场判定带一个宽限窗口，StrictMode `mount → cleanup → mount` 与切换形态时的瞬时全卸不会误取消。
 */
export function useAgentRunHost(
  host: AgentRunHostKind,
  onUnmount: AgentRunHostDetachReason = 'keep'
): void {
  // 卸载时读最新语义（父组件可能按「关闭 / 最小化」切换传值）
  const reasonRef = useRef(onUnmount)
  reasonRef.current = onUnmount

  useEffect(() => {
    useAgentRunStore.getState().attachHost(host)
    return () => {
      useAgentRunStore.getState().detachHost(host, reasonRef.current)
    }
  }, [host])
}

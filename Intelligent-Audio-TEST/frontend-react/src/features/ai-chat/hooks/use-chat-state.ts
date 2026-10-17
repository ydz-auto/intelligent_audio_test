/**
 * AI 对话会话状态（interfaces 层 hooks；08_AI对话页.md §3.1B/§3.7）。
 * 整页（/ai-chat）与全局浮窗两形态共用 infrastructure/stores/aiChatSessionStore 单一会话
 * 实例——§3.1B「两形态同 store 不分裂会话」（浮窗全局驻留含 /ai-chat，各持独立实例会以
 * 500ms 防抖互覆写 iatp:ai-chat:v1:* 键、丢消息）。config/messages 由 store 持有并订阅持久化。
 * URL 契约：/ai-chat?report={id} / /ai-chat?task={id} 绑定上下文并预填指令（§3.7）。
 */
import { useEffect, useState } from 'react'

import {
  useAiChatSession,
  type AiChatInitialContext,
} from '@/infrastructure/stores/aiChatSessionStore'

type InitialContext = AiChatInitialContext

/**
 * URL 入口预填指令（§3.7）：/ai-chat?report={id} 进入即预填「帮我把报告 #{id} 的测试结果
 * 生成一份可交付报告」；/ai-chat?task={id} 预填「帮我把任务 #{id} 的测试结果生成一份报告」。
 */
function buildInitialPrompt(context?: InitialContext): string | undefined {
  const report = context?.report
  const reportId = Number(report)
  if (report && Number.isFinite(reportId)) {
    return `帮我把报告 #${reportId} 的测试结果生成一份可交付报告`
  }
  const task = context?.task
  const taskId = Number(task)
  if (task && Number.isFinite(taskId)) {
    return `帮我把任务 #${taskId} 的测试结果生成一份报告`
  }
  return undefined
}

export function useChatState(context?: InitialContext) {
  const config = useAiChatSession((s) => s.config)
  const messages = useAiChatSession((s) => s.messages)
  const updateMessages = useAiChatSession((s) => s.updateMessages)
  const updateConfig = useAiChatSession((s) => s.updateConfig)
  const clearMessages = useAiChatSession((s) => s.clearMessages)
  const applyInitialContext = useAiChatSession((s) => s.applyInitialContext)

  // URL 契约（§3.7）：挂载时绑定 report/task 上下文（store 内做已存 config 优先/同上下文保持）
  useEffect(() => {
    applyInitialContext(context)
  }, [applyInitialContext, context])

  // 预填指令（页面级草稿，不入共享会话：浮窗无 URL 上下文，仅 /ai-chat 整页使用）
  const [initialPrompt] = useState(() => buildInitialPrompt(context))
  const [isLoadingMessages] = useState(false)

  return {
    config,
    messages,
    initialPrompt,
    isLoadingMessages,
    updateMessages,
    updateConfig,
    clearMessages,
  }
}

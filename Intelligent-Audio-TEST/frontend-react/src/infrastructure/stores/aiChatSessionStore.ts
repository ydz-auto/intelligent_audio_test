/**
 * AI 对话会话全局 store（infrastructure/stores 层；08_AI对话页.md §3.1B/§3.7）。
 * 整页（/ai-chat）与全局浮窗（AgentWorkbench）两形态共享同一会话——§3.1B「两形态同 store
 * 不分裂会话」：浮窗在登录壳全局驻留（含 /ai-chat 页），若两形态各持一套 useChatState，
 * 会分别以 500ms 防抖写同一组 iatp:ai-chat:v1:* 键、先后互覆写丢消息。收敛为 zustand
 * 全局实例 + 单写入点（订阅持久化），保证同键单实例写、切换形态不丢会话。
 * URL 契约（§3.7）：/ai-chat?report={id} / /ai-chat?task={id} 首访无存档时绑定一次上下文
 * （已存 config 优先；同上下文保持会话）。
 */
import { create } from 'zustand'

import type { ChatConfig, ChatMessage } from '@/domain/models/aiChat'
import { DEFAULT_CONFIG } from '@/features/ai-chat/constants'
import { aiChatPrefs } from '@/infrastructure/storage/aiChatPrefs'
import { MOCK_REPORTS } from '@/infrastructure/mock/ai-chat-mock'

/** URL 契约上下文（§3.7：/ai-chat?report={id} / /ai-chat?task={id}） */
export type AiChatInitialContext = {
  report?: string
  task?: string
}

function buildInitialConfig(context?: AiChatInitialContext): ChatConfig {
  const saved = aiChatPrefs.loadConfig()
  if (saved) return saved

  // URL 契约：/ai-chat?report={id} / /ai-chat?task={id}（§3.7）
  const report = context?.report
  const task = context?.task
  const reportId = Number(report)
  const taskId = Number(task)

  if (report && Number.isFinite(reportId)) {
    const found = MOCK_REPORTS.find((item) => item.id === reportId)
    if (found) {
      return {
        ...DEFAULT_CONFIG,
        reportContextId: String(found.id),
        reportContextLabel: found.name,
        reportContextType: found.type,
      }
    }
  }
  if (task && Number.isFinite(taskId)) {
    return {
      ...DEFAULT_CONFIG,
      reportContextId: String(taskId),
      reportContextLabel: `任务 #${taskId}`,
      reportContextType: 'task_context',
    }
  }
  return { ...DEFAULT_CONFIG }
}

type UpdateMessagesFn = (updater: (prev: ChatMessage[]) => ChatMessage[]) => void

type AiChatSessionState = {
  config: ChatConfig
  messages: ChatMessage[]
  /** 已应用的 URL 上下文 id（§3.7 首访/换上下文应用一次；防重复 set） */
  appliedContextKey?: string
  updateMessages: UpdateMessagesFn
  updateConfig: <K extends keyof ChatConfig>(key: K, value: ChatConfig[K]) => void
  clearMessages: () => void
  /** URL 契约（§3.7）：绑定 report/task 上下文（已存 config 优先；同上下文保持会话） */
  applyInitialContext: (context?: AiChatInitialContext) => void
}

export const useAiChatSession = create<AiChatSessionState>()((set, get) => ({
  config: aiChatPrefs.loadConfig() ?? { ...DEFAULT_CONFIG },
  messages: aiChatPrefs.loadMessages() ?? [],
  appliedContextKey: undefined,
  updateMessages: (updater) =>
    set((state) => ({ messages: updater(state.messages) })),
  updateConfig: (key, value) =>
    set((state) => ({ config: { ...state.config, [key]: value } })),
  clearMessages: () => set({ messages: [] }),
  applyInitialContext: (context) => {
    if (!context?.report && !context?.task) return
    const requestedId = context.report ?? context.task
    if (get().appliedContextKey === requestedId) return
    set({
      config: buildInitialConfig(context),
      appliedContextKey: requestedId,
    })
  },
}))

// 单写入点持久化（§3.7）：messages 500ms 防抖、config 即时；两形态共享同一实例，无互覆写。
let messageSaveTimer: number | null = null
useAiChatSession.subscribe((state, prev) => {
  if (state.messages !== prev.messages) {
    if (messageSaveTimer !== null) window.clearTimeout(messageSaveTimer)
    messageSaveTimer = window.setTimeout(() => {
      aiChatPrefs.saveMessages(state.messages)
    }, 500)
  }
  if (state.config !== prev.config) {
    aiChatPrefs.saveConfig(state.config)
  }
})

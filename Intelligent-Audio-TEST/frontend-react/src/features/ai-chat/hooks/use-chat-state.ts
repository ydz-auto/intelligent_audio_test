/**
 * AI 对话会话状态（interfaces 层 hooks；照 newAPI use-playground-state 平移）。
 * config/messages 两态 + 500ms 防抖持久化（§3.7 本地键；2026-10-17 新口径：
 * parameter-enabled 键废弃，config 改存模型/供应商选择 §3.5/§3.11）。
 * 首访无存档走规范空态（四 starter，§3.1/§3.3）；「清空对话」后同样回空态。
 * URL 契约：/ai-chat?report={id} 绑定报告上下文、/ai-chat?task={id} 绑定任务上下文并预填指令（§3.7）。
 */
import { useEffect, useRef, useState } from 'react'

import type {
  ChatConfig,
  ChatMessage,
} from '@/domain/models/aiChat'
import { DEFAULT_CONFIG } from '@/features/ai-chat/constants'
import { aiChatPrefs } from '@/infrastructure/storage/aiChatPrefs'
import { MOCK_REPORTS } from '@/infrastructure/mock/ai-chat-mock'

type InitialContext = {
  report?: string
  task?: string
}

function buildInitialConfig(context?: InitialContext): ChatConfig {
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

/** URL 任务入口预填指令（§3.7：/ai-chat?task={id} 进入即预填「帮我把任务 #{id} 的测试结果生成一份报告」） */
function buildInitialPrompt(context?: InitialContext): string | undefined {
  const task = context?.task
  const taskId = Number(task)
  if (task && Number.isFinite(taskId)) {
    return `帮我把任务 #${taskId} 的测试结果生成一份报告`
  }
  return undefined
}

export function useChatState(context?: InitialContext) {
  const [config, setConfig] = useState<ChatConfig>(() =>
    buildInitialConfig(context)
  )
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    const saved = aiChatPrefs.loadMessages()
    return saved && saved.length > 0 ? saved : []
  })
  const [initialPrompt] = useState(() => buildInitialPrompt(context))
  const [isLoadingMessages] = useState(false)
  const [isHydrated] = useState(true)

  const saveTimerRef = useRef<number | null>(null)

  // 500ms 防抖持久化（照 use-playground-state）
  useEffect(() => {
    if (!isHydrated) return
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current)
    }
    saveTimerRef.current = window.setTimeout(() => {
      aiChatPrefs.saveMessages(messages)
    }, 500)
    return () => {
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current)
      }
    }
  }, [messages, isHydrated])

  useEffect(() => {
    aiChatPrefs.saveConfig(config)
  }, [config])

  const updateMessages = (updater: (prev: ChatMessage[]) => ChatMessage[]) => {
    setMessages((prev) => updater(prev))
  }

  const updateConfig = <K extends keyof ChatConfig>(
    key: K,
    value: ChatConfig[K]
  ) => {
    setConfig((prev) => ({ ...prev, [key]: value }))
  }

  const clearMessages = () => {
    setMessages([])
  }

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

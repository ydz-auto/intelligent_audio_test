/**
 * AI 对话会话状态（interfaces 层 hooks；照 newAPI use-playground-state 平移）。
 * config/messages/parameterEnabled 三态 + 500ms 防抖持久化（§3.7 本地三键）。
 * 首访无存档时播种演示会话（可视稿展示用）；「清空对话」后回规范空态。
 */
import { useEffect, useRef, useState } from 'react'

import type {
  ChatConfig,
  ChatMessage,
  ChatParameterEnabled,
} from '@/domain/models/aiChat'
import {
  DEFAULT_CONFIG,
  DEFAULT_PARAMETER_ENABLED,
} from '@/features/ai-chat/constants'
import { aiChatPrefs } from '@/infrastructure/storage/aiChatPrefs'
import { DEMO_MESSAGES, MOCK_REPORTS } from '@/infrastructure/mock/ai-chat-mock'

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
        reportContextType: 'test-report',
      }
    }
  }
  if (task && Number.isFinite(taskId)) {
    return {
      ...DEFAULT_CONFIG,
      reportContextId: String(taskId),
      reportContextLabel: `任务 #${taskId}`,
      reportContextType: 'task',
    }
  }
  return { ...DEFAULT_CONFIG }
}

export function useChatState(context?: InitialContext) {
  const [config, setConfig] = useState<ChatConfig>(() =>
    buildInitialConfig(context)
  )
  const [parameterEnabled, setParameterEnabled] = useState<ChatParameterEnabled>(
    () => aiChatPrefs.loadParameterEnabled() ?? { ...DEFAULT_PARAMETER_ENABLED }
  )
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    const saved = aiChatPrefs.loadMessages()
    return saved && saved.length > 0 ? saved : DEMO_MESSAGES
  })
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

  useEffect(() => {
    aiChatPrefs.saveParameterEnabled(parameterEnabled)
  }, [parameterEnabled])

  const updateMessages = (updater: (prev: ChatMessage[]) => ChatMessage[]) => {
    setMessages((prev) => updater(prev))
  }

  const updateConfig = <K extends keyof ChatConfig>(
    key: K,
    value: ChatConfig[K]
  ) => {
    setConfig((prev) => ({ ...prev, [key]: value }))
  }

  const updateParameterEnabled = (key: keyof ChatParameterEnabled, value: boolean) => {
    setParameterEnabled((prev) => ({ ...prev, [key]: value }))
  }

  const clearMessages = () => {
    setMessages([])
  }

  return {
    config,
    parameterEnabled,
    messages,
    isLoadingMessages,
    updateMessages,
    updateConfig,
    updateParameterEnabled,
    clearMessages,
  }
}

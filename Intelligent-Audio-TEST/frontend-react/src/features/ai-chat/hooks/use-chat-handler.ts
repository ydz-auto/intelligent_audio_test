/**
 * AI 对话发送/停止（interfaces 层 hooks；照 newAPI use-chat-handler/use-stream-request
 * 平移流式骨架——**Demo 态对话由用户自配 LLM 供应商驱动**（§3.8「Demo 可先行」，
 * §3.11/§3.10 红线「不做假数据回显」）。
 * 2026-10-17 审计返修（P1）：删除本地 mock 回显与杜撰工具卡/来源（通过率 92.3% 等
 * 假数值），发送真实 POST /chat/completions（llmProviderApi.sendChatCompletion），
 * 正文本地逐块渲染模拟打字机；无供应商/无模型 → 语义化错误消息；Agent 工具链待后端立项。
 * 2026-10-17 新口径：无模型参数（仅模型/供应商切换），发送体不带 parameterEnabled。
 */
import { useCallback, useRef, useState } from 'react'

import type {
  ChatConfig,
  ChatMessage,
  LlmProvider,
} from '@/domain/models/aiChat'
import { ERROR_MESSAGES, MESSAGE_STATUS } from '@/features/ai-chat/constants'
import {
  sendChatCompletion,
  type ChatCompletionMessage,
} from '@/infrastructure/api/llmProviderApi'

type UpdateMessagesFn = (updater: (prev: ChatMessage[]) => ChatMessage[]) => void

/** Demo 系统提示（中文；不注入杜撰报告事实，数值一律由真实回复承载） */
const SYSTEM_PROMPT =
  '你是智能音频测试平台的灵犀Agent，帮助用户生成、对比、解读测试报告。回答简洁专业，不确定的信息不要编造。'

/** 流式合帧节奏（照 STREAM_UPDATE_FLUSH_MS=50 语义；真实回复本地逐块渲染） */
const STREAM_CHUNK_MS = 40
const STREAM_CHUNK_SIZE = 12

/** 组装 OpenAI 兼容 messages（系统提示 + 历史完整消息 + 当前输入） */
function buildChatHistory(
  messages: ChatMessage[],
  text: string
): ChatCompletionMessage[] {
  const history: ChatCompletionMessage[] = [
    { role: 'system', content: SYSTEM_PROMPT },
  ]
  for (const message of messages) {
    if (
      message.from !== 'user' &&
      message.from !== 'assistant'
    ) {
      continue
    }
    if (message.status === 'loading' || message.status === 'error') continue
    const content = message.versions[message.versions.length - 1]?.content
    if (!content) continue
    history.push({
      role: message.from === 'user' ? 'user' : 'assistant',
      content,
    })
  }
  history.push({ role: 'user', content: text })
  return history
}

function buildLoadingMessage(key: string): ChatMessage {
  const now = Date.now()
  return {
    key,
    from: 'assistant',
    versions: [{ id: `${key}-v1`, content: '' }],
    createdAt: now,
    startedAt: now,
    status: MESSAGE_STATUS.LOADING,
  }
}

export function useChatHandler({
  config,
  provider,
  messages,
  onMessageUpdate,
}: {
  config: ChatConfig
  /** 当前供应商（调用方从 useLlmProviders 解析：config.providerId 命中或默认） */
  provider: LlmProvider | null
  messages: ChatMessage[]
  onMessageUpdate: UpdateMessagesFn
}) {
  const [isGenerating, setIsGenerating] = useState(false)
  const runRef = useRef<number | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const timersRef = useRef<number[]>([])

  // 最新闭包值（useCallback 内读取避免陈旧）
  const configRef = useRef(config)
  configRef.current = config
  const providerRef = useRef(provider)
  providerRef.current = provider
  const messagesRef = useRef(messages)
  messagesRef.current = messages

  const schedule = useCallback((fn: () => void, delay: number) => {
    const id = window.setTimeout(fn, delay)
    timersRef.current.push(id)
    return id
  }, [])

  const cancelTimers = useCallback(() => {
    timersRef.current.forEach((id) => window.clearTimeout(id))
    timersRef.current = []
  }, [])

  const stopGeneration = useCallback(() => {
    if (runRef.current === null) return
    runRef.current = null
    cancelTimers()
    abortRef.current?.abort()
    abortRef.current = null
    // 停止后保留已生成内容，标记 complete（playground stop 语义）
    onMessageUpdate((prev) =>
      prev.map((message) => {
        if (
          message.status === MESSAGE_STATUS.LOADING ||
          message.status === MESSAGE_STATUS.STREAMING
        ) {
          return {
            ...message,
            status: MESSAGE_STATUS.COMPLETE,
            completedAt: Date.now(),
            durationMs: message.startedAt
              ? Date.now() - message.startedAt
              : 0,
            isReasoningStreaming: false,
          }
        }
        return message
      })
    )
    setIsGenerating(false)
  }, [cancelTimers, onMessageUpdate])

  const sendChat = useCallback(
    (text: string) => {
      if (runRef.current !== null) return

      const userKey = `user-${Date.now()}`
      const assistantKey = `assistant-${Date.now()}`
      const userMessage: ChatMessage = {
        key: userKey,
        from: 'user',
        versions: [{ id: `${userKey}-v1`, content: text }],
        createdAt: Date.now(),
      }
      const loadingMessage = buildLoadingMessage(assistantKey)
      onMessageUpdate((prev) => [...prev, userMessage, loadingMessage])
      setIsGenerating(true)

      const runId = Date.now()
      runRef.current = runId
      const isInterrupted = () => runRef.current !== runId

      const patch = (partial: Partial<ChatMessage>) => {
        if (isInterrupted()) return
        onMessageUpdate((prev) =>
          prev.map((message) =>
            message.key === assistantKey ? { ...message, ...partial } : message
          )
        )
      }

      /** 落语义化错误消息（无供应商/无模型/网络失败等；不杜撰数据回显） */
      const fail = (message: string) => {
        if (isInterrupted()) return
        patch({
          versions: [{ id: `${assistantKey}-v1`, content: message }],
          status: MESSAGE_STATUS.ERROR,
          completedAt: Date.now(),
        })
        runRef.current = null
        abortRef.current = null
        setIsGenerating(false)
      }

      // 前置校验：对话由用户自配 LLM 供应商驱动（§3.11）
      const currentProvider = providerRef.current
      const currentModel = configRef.current.modelId
      if (
        !currentProvider ||
        !currentProvider.baseUrl ||
        !currentProvider.apiKey
      ) {
        fail(ERROR_MESSAGES.noProviderChat)
        return
      }
      if (!currentModel) {
        fail(ERROR_MESSAGES.noModel)
        return
      }

      const abort = new AbortController()
      abortRef.current = abort

      void (async () => {
        try {
          const content = await sendChatCompletion({
            baseUrl: currentProvider.baseUrl,
            apiKey: currentProvider.apiKey,
            model: currentModel,
            messages: buildChatHistory(messagesRef.current, text),
            signal: abort.signal,
          })
          if (isInterrupted()) return

          // 正文逐块本地渲染（打字机；真实回复，无杜撰工具卡/来源）
          let index = 0
          patch({
            versions: [{ id: `${assistantKey}-v1`, content: '' }],
            status: MESSAGE_STATUS.STREAMING,
          })
          const stream = () => {
            if (isInterrupted()) return
            index += STREAM_CHUNK_SIZE
            patch({
              versions: [
                { id: `${assistantKey}-v1`, content: content.slice(0, index) },
              ],
            })
            if (index < content.length) {
              schedule(stream, STREAM_CHUNK_MS)
            } else {
              // 先落终态再清 runRef：patch 以 isInterrupted 守卫，清 ref 在前会把终态补丁吞掉
              patch({
                status: MESSAGE_STATUS.COMPLETE,
                completedAt: Date.now(),
                durationMs: Date.now() - (loadingMessage.startedAt ?? Date.now()),
              })
              runRef.current = null
              abortRef.current = null
              setIsGenerating(false)
            }
          }
          schedule(stream, 120)
        } catch (err) {
          if (isInterrupted()) return
          const message =
            err instanceof Error && err.message
              ? err.message
              : ERROR_MESSAGES.generic
          fail(message)
        }
      })()
    },
    [onMessageUpdate, schedule]
  )

  return {
    sendChat,
    stopGeneration,
    isGenerating,
    // Demo 态对话由用户自配 LLM 供应商驱动（§3.11），无平台后端依赖
    pendingRequest: { config },
  }
}

/**
 * AI 对话发送/停止（interfaces 层 hooks；08_AI对话页.md §3.8 + INT-2457 M0）。
 *
 * 两条通道（§12.2，默认由配置决定 = 平台 Agent）：
 * - platform：POST /agent/sessions/{id}/runs + GET /agent/runs/{id}/events（SSE），
 *   事件流（message_delta / tool_call / tool_result / run_finished / error）驱动消息渲染；
 *   取消走 POST /agent/runs/{id}/cancel（同一 run 只发一次），断线续传与去重在
 *   application/agent/use-agent-run。
 * - provider：保留「用户自配 LLM 供应商直连」降级模式（P0-1 拍板后二选一，不长期双轨）；
 *   正文本地逐块渲染模拟打字机（既有行为，未接平台后端）。
 *
 * 红线：不写 mock、不杜撰工具卡/来源；无供应商 / Agent 未开启 / 未部署均落语义化错误。
 */
import { useCallback, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  AGENT_ERROR_COPY,
  AGENT_EVENT_TYPE,
  AGENT_RUN_STATUS,
  type AgentRunEvent,
  type AgentRunStatus,
} from '@/domain/models/agent'
import {
  CHAT_CHANNEL,
  type ChatChannel,
  type ChatConfig,
  type ChatMessage,
  type LlmProvider,
} from '@/domain/models/aiChat'
import { useAgentRun } from '@/application/agent/use-agent-run'
import {
  AGENT_TOOL_LABELS,
  AGENT_RUN_PHASE_COPY,
  ERROR_MESSAGES,
  MESSAGE_STATUS,
} from '@/features/ai-chat/constants'
import {
  sendChatCompletion,
  type ChatCompletionMessage,
} from '@/infrastructure/api/llmProviderApi'

type UpdateMessagesFn = (updater: (prev: ChatMessage[]) => ChatMessage[]) => void

/** sendChat 选项（重新生成=截断重建 §3.4：请求体用截断后数组构造，不残留旧 assistant 回复） */
export type SendChatOptions = {
  /** 请求体历史覆盖：传截断后数组，缺省用当前 messages（重新生成专用） */
  historyMessages?: ChatMessage[]
  /** 是否追加新 user 消息（重新生成时 false：原 user 指令已在截断数组内，只补 assistant 占位） */
  appendUserMessage?: boolean
}

/** Demo 系统提示（中文；主推全部能力——2026-10-17 08:06 负责人口径；仅供应商通道使用） */
const SYSTEM_PROMPT =
  '你是智能音频测试平台的灵犀Agent，帮助用户完成平台各类事务：报告生成/对比/分析、用例生成、音频导入、任务管理、设备驱动、日志诊断等。回答简洁专业，不确定的信息不要编造。'

/** 流式合帧节奏（供应商通道：真实回复本地逐块渲染） */
const STREAM_CHUNK_MS = 40
const STREAM_CHUNK_SIZE = 12

/** 组装 OpenAI 兼容 messages（系统提示 + 历史完整消息 + 当前输入） */
function buildChatHistory(
  messages: ChatMessage[],
  text: string,
  systemPrompt = SYSTEM_PROMPT
): ChatCompletionMessage[] {
  const history: ChatCompletionMessage[] = [
    { role: 'system', content: systemPrompt },
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

/** 平台 Agent 通道：run 终态 → 消息状态补丁（保留已生成正文，仅标终态徽标） */
function toTerminalPatch(
  status: AgentRunStatus,
  startedAt: number | undefined,
  now: number
): Partial<ChatMessage> {
  return {
    status: MESSAGE_STATUS.COMPLETE,
    runStatus: status,
    completedAt: now,
    durationMs: startedAt ? now - startedAt : 0,
    isReasoningStreaming: false,
  }
}

export function useChatHandler({
  config,
  provider,
  messages,
  onMessageUpdate,
  /** 系统提示覆盖（AI 复核等有界会话注入专用上下文；仅供应商通道） */
  systemPrompt,
  /** 对话通道（缺省 = 自带供应商，保持既有调用方行为；页面按配置传平台 Agent） */
  channel = CHAT_CHANNEL.PROVIDER,
}: {
  config: ChatConfig
  /** 当前供应商（调用方从 useLlmProviders 解析：config.providerId 命中或默认） */
  provider: LlmProvider | null
  messages: ChatMessage[]
  onMessageUpdate: UpdateMessagesFn
  systemPrompt?: string
  channel?: ChatChannel
}) {
  const [isGenerating, setIsGenerating] = useState(false)
  const runRef = useRef<number | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const timersRef = useRef<number[]>([])

  /** 平台通道：当前 assistant 消息补丁器（新一轮发送时重置） */
  const patchAssistantRef = useRef<
    ((updater: (message: ChatMessage) => ChatMessage) => void) | null
  >(null)
  /** 平台通道：已累积正文（message_delta 逐段拼接） */
  const contentRef = useRef('')

  // 最新闭包值（useCallback 内读取避免陈旧）
  const configRef = useRef(config)
  configRef.current = config
  const providerRef = useRef(provider)
  providerRef.current = provider
  const messagesRef = useRef(messages)
  messagesRef.current = messages
  const systemPromptRef = useRef(systemPrompt)
  systemPromptRef.current = systemPrompt
  const channelRef = useRef(channel)
  channelRef.current = channel

  const schedule = useCallback((fn: () => void, delay: number) => {
    const id = window.setTimeout(fn, delay)
    timersRef.current.push(id)
    return id
  }, [])

  const cancelTimers = useCallback(() => {
    timersRef.current.forEach((id) => window.clearTimeout(id))
    timersRef.current = []
  }, [])

  /** 平台通道事件 → 消息补丁（去重已在 use-agent-run 完成） */
  const handleAgentEvent = useCallback((event: AgentRunEvent) => {
    switch (event.type) {
      case AGENT_EVENT_TYPE.MESSAGE_DELTA: {
        contentRef.current += event.delta
        const content = contentRef.current
        patchAssistantRef.current?.((message) => ({
          ...message,
          status: MESSAGE_STATUS.STREAMING,
          startedAt: message.startedAt ?? Date.now(),
          versions: [
            { id: message.versions[0]?.id ?? `${message.key}-v1`, content },
          ],
        }))
        return
      }
      case AGENT_EVENT_TYPE.TOOL_CALL: {
        patchAssistantRef.current?.((message) => {
          const existing = message.toolCalls ?? []
          const call = {
            id: event.toolCallId,
            tool: event.tool,
            label: AGENT_TOOL_LABELS[event.tool] ?? event.tool,
            status: 'running' as const,
            summary: event.summary,
          }
          const next = existing.some((item) => item.id === call.id)
            ? existing.map((item) => (item.id === call.id ? { ...item, ...call } : item))
            : [...existing, call]
          return { ...message, toolCalls: next }
        })
        return
      }
      case AGENT_EVENT_TYPE.TOOL_RESULT: {
        patchAssistantRef.current?.((message) => ({
          ...message,
          toolCalls: (message.toolCalls ?? []).map((call) =>
            call.id === event.toolCallId
              ? {
                  ...call,
                  status:
                    event.status === 'SUCCEEDED'
                      ? ('completed' as const)
                      : ('error' as const),
                  summary: event.summary ?? call.summary,
                  errorCode: event.errorCode,
                  sourceRefs: event.sourceRefs ?? call.sourceRefs,
                }
              : call
          ),
        }))
        return
      }
      case AGENT_EVENT_TYPE.RUN_FINISHED: {
        const patch = patchAssistantRef.current
        const now = Date.now()
        patch?.((message) =>
          message.versions[0]?.content || contentRef.current
            ? { ...message, ...toTerminalPatch(event.status, message.startedAt, now) }
            : {
                ...message,
                ...toTerminalPatch(event.status, message.startedAt, now),
                versions: [
                  {
                    id: message.versions[0]?.id ?? `${message.key}-v1`,
                    content:
                      event.status === AGENT_RUN_STATUS.CANCELLED
                        ? AGENT_RUN_PHASE_COPY.cancelled
                        : event.error || AGENT_ERROR_COPY.runFailed,
                  },
                ],
              }
        )
        patchAssistantRef.current = null
        setIsGenerating(false)
        runRef.current = null
        return
      }
      default:
        // run_started / approval_required（M2）/ context_compacted：不改变消息正文
        return
    }
  }, [])

  const handleAgentError = useCallback((message: string) => {
    patchAssistantRef.current?.((current) => ({
      ...current,
      status: MESSAGE_STATUS.ERROR,
      errorCode: 'AGENT_ERROR',
      versions: [
        {
          id: current.versions[0]?.id ?? `${current.key}-v1`,
          content: message,
        },
      ],
      completedAt: Date.now(),
      durationMs: current.startedAt ? Date.now() - current.startedAt : 0,
    }))
    patchAssistantRef.current = null
    setIsGenerating(false)
    runRef.current = null
  }, [])

  const agentRun = useAgentRun({
    onEvent: handleAgentEvent,
    onError: handleAgentError,
  })

  const stopGeneration = useCallback(() => {
    if (channelRef.current === CHAT_CHANNEL.PLATFORM) {
      // 平台通道：取消由后端下发 CANCELLED 终态；同一 run 只发一次取消请求（use-agent-run 兜底）
      void agentRun.cancel().then((failure) => {
        if (failure) toast.error(failure)
      })
      return
    }
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
  }, [agentRun, cancelTimers, onMessageUpdate])

  /** 平台通道发送：补 user 消息 + assistant 占位，run 事件驱动后续渲染 */
  const sendPlatformChat = useCallback(
    (text: string, options?: SendChatOptions) => {
      if (runRef.current !== null) return
      const appendUserMessage = options?.appendUserMessage ?? true
      const userKey = `user-${Date.now()}`
      const assistantKey = `assistant-${Date.now()}`
      const userMessage: ChatMessage = {
        key: userKey,
        from: 'user',
        versions: [{ id: `${userKey}-v1`, content: text }],
        createdAt: Date.now(),
      }
      const loadingMessage = buildLoadingMessage(assistantKey)
      onMessageUpdate((prev) => [
        ...(appendUserMessage ? [...prev, userMessage] : prev),
        loadingMessage,
      ])
      setIsGenerating(true)
      const runToken = Date.now()
      runRef.current = runToken
      contentRef.current = ''
      patchAssistantRef.current = (updater) => {
        if (runRef.current !== runToken) return
        onMessageUpdate((prev) =>
          prev.map((message) =>
            message.key === assistantKey ? updater(message) : message
          )
        )
      }
      void agentRun.send(text)
    },
    [agentRun, onMessageUpdate]
  )

  const sendChat = useCallback(
    (text: string, options?: SendChatOptions) => {
      if (channelRef.current === CHAT_CHANNEL.PLATFORM) {
        sendPlatformChat(text, options)
        return
      }
      // ===== 供应商通道（降级模式，既有行为保持） =====
      if (runRef.current !== null) return

      const appendUserMessage = options?.appendUserMessage ?? true
      const userKey = `user-${Date.now()}`
      const assistantKey = `assistant-${Date.now()}`
      const userMessage: ChatMessage = {
        key: userKey,
        from: 'user',
        versions: [{ id: `${userKey}-v1`, content: text }],
        createdAt: Date.now(),
      }
      const loadingMessage = buildLoadingMessage(assistantKey)
      // 重新生成时原 user 指令已在截断数组内，只补 assistant 占位（§3.4 截断重建）
      onMessageUpdate((prev) => [
        ...(appendUserMessage ? [...prev, userMessage] : prev),
        loadingMessage,
      ])
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
            // 重新生成=截断重建（§3.4）：请求体用截断后历史构造，旧 assistant 回复不残留
            messages: buildChatHistory(
              options?.historyMessages ?? messagesRef.current,
              text,
              systemPromptRef.current
            ),
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
    [onMessageUpdate, schedule, sendPlatformChat]
  )

  /** 清空对话：平台通道同时结束当前会话上下文（下次发送新建会话） */
  const resetChat = useCallback(() => {
    cancelTimers()
    abortRef.current?.abort()
    abortRef.current = null
    runRef.current = null
    patchAssistantRef.current = null
    contentRef.current = ''
    agentRun.reset()
    setIsGenerating(false)
  }, [agentRun, cancelTimers])

  const isCancelling = agentRun.phase === 'cancelling'

  return {
    sendChat,
    stopGeneration,
    isGenerating,
    /** 取消请求在途（输入区停止钮禁用，防重复） */
    isCancelling,
    /** 平台通道生命周期（reconnecting 时页面显示重连提示） */
    runPhase: agentRun.phase,
    /** 当前 run（终态含 CANCELLED / FAILED） */
    run: agentRun.run,
    resetChat,
    // Demo 态对话由用户自配 LLM 供应商驱动（§3.11），无平台后端依赖
    pendingRequest: { config },
  }
}

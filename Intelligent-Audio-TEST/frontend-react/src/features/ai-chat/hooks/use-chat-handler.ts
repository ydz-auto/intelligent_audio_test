/**
 * AI 对话发送/停止（interfaces 层 hooks；照 newAPI use-chat-handler/use-stream-request
 * 平移流式骨架——先本地回显 mock 流式，DSH 接线待后端立项）。
 * 流程：追加 user 消息 + loading 占位 → 推理 → 工具卡 → 内容逐块流式 → complete。
 */
import { useCallback, useRef, useState } from 'react'

import type {
  AgentToolCall,
  ChatConfig,
  ChatMessage,
  ChatParameterEnabled,
} from '@/domain/models/aiChat'
import { MESSAGE_STATUS } from '@/features/ai-chat/constants'
import {
  MOCK_AGENT_REPLY,
  MOCK_AGENT_SHORT_REPLY,
  MOCK_REASONING_CONTENT,
} from '@/infrastructure/mock/ai-chat-mock'

type UpdateMessagesFn = (updater: (prev: ChatMessage[]) => ChatMessage[]) => void

const REASONING_DELAY_MS = 400
const TOOL_START_MS = 1100
const TOOL_END_MS = 1900
/** 流式合帧节奏（照 STREAM_UPDATE_FLUSH_MS=50 语义，本地逐块更粗） */
const STREAM_CHUNK_MS = 55
const STREAM_CHUNK_SIZE = 3

function pickReply(prompt: string): string {
  if (/(生成|解读|分析|报告)/.test(prompt)) return MOCK_AGENT_REPLY
  return MOCK_AGENT_SHORT_REPLY
}

function pickToolCalls(prompt: string): AgentToolCall[] {
  if (/(对比)/.test(prompt)) {
    return [
      {
        id: `tool-${Date.now()}-1`,
        tool: 'compare_reports',
        label: '对比报告',
        status: 'completed',
        summary: '对比 T315 与 T320 两份测试报告：通过率 -5.6pp，主要差异集中在远场噪声场景。',
      },
    ]
  }
  return [
    {
      id: `tool-${Date.now()}-1`,
      tool: 'report_get_facts',
      label: '读取报告数据',
      status: 'completed',
      summary: '报告 #320（T320 唤醒词识别回归）：156 用例，通过 144，通过率 92.3%。',
    },
    {
      id: `tool-${Date.now()}-2`,
      tool: 'report_query_metrics',
      label: '查询报告指标',
      status: 'completed',
      summary: '首唤醒延迟 P50=412ms；误唤醒率 1.8%；远场 3m+55dB 通过率 61%。',
    },
  ]
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
    reasoning: { content: '', duration: 0 },
    isReasoningStreaming: true,
  }
}

export function useChatHandler({
  config,
  parameterEnabled,
  onMessageUpdate,
}: {
  config: ChatConfig
  parameterEnabled: ChatParameterEnabled
  onMessageUpdate: UpdateMessagesFn
}) {
  const [isGenerating, setIsGenerating] = useState(false)
  const runRef = useRef<number | null>(null)
  const timersRef = useRef<number[]>([])

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
    // 停止后保留已生成内容，标记 complete（playground stop 语义）
    onMessageUpdate((prev) =>
      prev.map((message) => {
        if (message.status === MESSAGE_STATUS.LOADING || message.status === MESSAGE_STATUS.STREAMING) {
          return {
            ...message,
            status: MESSAGE_STATUS.COMPLETE,
            completedAt: Date.now(),
            durationMs: (message.startedAt ? Date.now() - message.startedAt : 0),
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

      const reply = pickReply(text)
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

      // 1) 推理完成
      schedule(() => {
        if (isInterrupted()) return
        patch({
          reasoning: { content: MOCK_REASONING_CONTENT, duration: 2 },
          isReasoningStreaming: false,
          status: MESSAGE_STATUS.STREAMING,
        })
      }, REASONING_DELAY_MS)

      // 2) 工具卡 running
      schedule(() => {
        if (isInterrupted()) return
        patch({
          toolCalls: pickToolCalls(text).map((tool) => ({
            ...tool,
            status: 'running' as const,
          })),
        })
      }, TOOL_START_MS)

      // 3) 工具卡 completed
      schedule(() => {
        if (isInterrupted()) return
        patch({
          toolCalls: pickToolCalls(text).map((tool) => ({
            ...tool,
            status: 'completed' as const,
          })),
        })
      }, TOOL_END_MS)

      // 4) 正文逐块流式
      let index = 0
      const stream = () => {
        if (isInterrupted()) return
        index += STREAM_CHUNK_SIZE
        patch({
          versions: [
            {
              id: `${assistantKey}-v1`,
              content: reply.slice(0, index),
            },
          ],
          status: MESSAGE_STATUS.STREAMING,
        })
        if (index < reply.length) {
          schedule(stream, STREAM_CHUNK_MS)
        } else {
          runRef.current = null
          setIsGenerating(false)
          patch({
            status: MESSAGE_STATUS.COMPLETE,
            completedAt: Date.now(),
            durationMs: Date.now() - (loadingMessage.startedAt ?? Date.now()),
            sourceRefs: [
              { reportId: 320, metricId: 'pass_rate', dataVersion: 'v3', verified: true },
              { reportId: 320, metricId: 'farfield_55db', dataVersion: 'v2', verified: false },
            ],
          })
        }
      }
      schedule(stream, TOOL_END_MS + 200)
    },
    [onMessageUpdate, schedule]
  )

  return {
    sendChat,
    stopGeneration,
    isGenerating,
    // 生成参数随会话请求透传 DSH（§3.8 占位；仅形态声明，mock 阶段不参与流式）
    pendingParameters: { config, parameterEnabled },
  }
}

/**
 * 复核会话编排 hook（application/ai-review，19 规范 §5.2/§5.4/§5.9，INT-1064）。
 * 灵犀Agent 复核会话（内嵌 Dialog）：与 /ai-chat 同一条平台 Agent 通道、同一份服务端
 * 模型供应商配置（模型/供应商切换器同源），但**独立有界会话**——每个用例一份内存态
 * 会话（ephemeral chat session + 独立 run store），不写主会话、关闭重开即新会话。
 * 打开时以「复核上下文摘要卡」呈现上下文（§5.3）+ 首条用户指令预填（可编辑）；
 * 多轮追问 →「保存复核结论」落位 ai_reviews（真实端点）→ 采纳/驳回闭环（§5.5）。
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'

import {
  createAgentRunStore,
  type AgentRunStore,
} from '@/application/agent/agent-run-store'
import { CHAT_CHANNEL } from '@/domain/models/aiChat'
import { createEphemeralAiChatPrefs } from '@/infrastructure/storage/aiChatPrefs'
import {
  createAiChatSessionStore,
  useAiChatSession,
  type AiChatSessionStore,
} from '@/infrastructure/stores/aiChatSessionStore'
import { useChatHandler } from '@/features/ai-chat/hooks/use-chat-handler'
import { useChatConversation } from '@/features/ai-chat/hooks/use-chat-conversation'

import { useAiReview } from '@/application/ai-review/use-ai-review'
import { useAiReviewContext } from '@/application/ai-review/use-ai-review-context'
import {
  buildContextSummaryMessage,
  buildReviewSystemPrompt,
  REVIEW_INITIAL_PROMPT,
} from '@/features/ai-review/constants'

/** 单个复核 scope 的运行态（内存态；关窗即弃，不落 localStorage） */
type ReviewSessionStores = {
  chat: AiChatSessionStore
  run: AgentRunStore
}

/** scope（taskId:caseId）→ 会话；同 scope 的多次打开共用一份（打开边沿再清空） */
const reviewSessionStores = new Map<string, ReviewSessionStores>()

function getReviewSessionStores(scopeKey: string): ReviewSessionStores {
  let stores = reviewSessionStores.get(scopeKey)
  if (!stores) {
    const chat = createAiChatSessionStore(createEphemeralAiChatPrefs())
    stores = { chat, run: createAgentRunStore(chat) }
    reviewSessionStores.set(scopeKey, stores)
  }
  return stores
}

export function useAiReviewSession({
  taskId,
  caseId,
  open,
  dimensionIds,
}: {
  taskId: number
  caseId: string
  open: boolean
  /** INT-1279：用例评估维度 id（保存复核结论显式传 dimension_ids，真实库结果无 LLM 判分维度时不 400） */
  dimensionIds?: number[]
}) {
  const navigate = useNavigate()
  const stores = getReviewSessionStores(`${taskId}:${caseId}`)
  const config = stores.chat((s) => s.config)
  const messages = stores.chat((s) => s.messages)
  const [providerManagerOpen, setProviderManagerOpen] = useState(false)
  const [draftText, setDraftText] = useState('')

  const contextQuery = useAiReviewContext(taskId, caseId, open)
  const ai = useAiReview(taskId, caseId)
  const context = contextQuery.context

  /** 打开时重置状态机 + 每次打开为全新有界会话（§5.2 关闭即释放；scope 独立不残留）。 */
  const wasOpenRef = useRef(open)
  useEffect(() => {
    if (open && !wasOpenRef.current) {
      stores.chat.getState().clearMessages()
      stores.run.getState().reset()
      ai.reset()
      setDraftText('')
    }
    wasOpenRef.current = open
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, stores])

  const { sendChat, stopGeneration, isGenerating, resetChat } = useChatHandler({
    config,
    messages,
    // 平台 Agent 通道：模型/供应商走服务端「模型供应商」（与 /ai-chat 统一），
    // 复核上下文按本轮请求前缀注入（平台通道无 system 消息位）。
    channel: CHAT_CHANNEL.PLATFORM,
    runStore: stores.run,
    requestPrefix: context ? buildReviewSystemPrompt(context) : null,
    onMessageUpdate: (updater) => stores.chat.getState().updateMessages(updater),
  })
  const {
    editingMessageKey,
    handleSendMessage,
    handleRegenerateMessage,
    handleEditMessage,
    handleEditPromptMessage,
    handleEditOpenChange,
    applyEdit,
    handleDeleteMessage,
    handleUndoMessage,
  } = useChatConversation({
    messages,
    updateMessages: (updater) => stores.chat.getState().updateMessages(updater),
    sendChat,
  })

  /** 首条用户指令预填（§5.3 预填可编辑；上下文就绪后落一次） */
  useEffect(() => {
    if (!open || !context) return
    if (draftText !== '') return
    setDraftText(REVIEW_INITIAL_PROMPT)
  }, [open, context, draftText])

  /** Agent 已产出分析（存在完整/流式中的 assistant 回复）——「保存复核结论」前置（§5.4） */
  const agentAnalyzed =
    messages.some(
      (m) =>
        m.from === 'assistant' &&
        (m.status === 'complete' || m.status === 'streaming') &&
        (m.versions[0]?.content ?? '').trim().length > 0
    )

  /** 保存复核结论前置：Agent 已分析且未在保存中/未保存过（§5.4「未生成结论时按钮禁用」） */
  const canSave = agentAnalyzed && ai.phase === 'idle'

  /** 保存复核结论（POST /tasks/results/ai-review；result_ids = 该用例执行结果；
   * dimension_ids = 用例评估维度（INT-1279：真实库结果无 LLM 判分维度时显式传，避免 400）；
   * 已有 AI 复核结论时 force=true 绕过幂等复用，§5.4「重新复核」） */
  const handleSave = () => {
    if (!context || context.deviceResults.length === 0) return
    void ai.save({
      resultIds: context.deviceResults.map((r) => r.id),
      dimensionIds: dimensionIds?.length ? dimensionIds : undefined,
      force: context.existingReviews.length > 0 ? true : undefined,
    })
  }

  /** 快捷追问 chips（§5.4：照 08 §3.4 Suggestion 语义，点击即发送） */
  const handleAskQuick = (text: string) => {
    handleSendMessage(text)
  }

  /** 展开到 /ai-chat：把复核上下文摘要 + 会话并入主会话并导航（08 §3.7 URL 契约扩展） */
  const expandToAiChat = () => {
    if (!context) return
    const main = useAiChatSession.getState()
    const now = Date.now()
    // 并入主会话：复核上下文摘要（首条 assistant，供主会话 LLM/用户继续追问）+ 复核会话消息
    const contextMsg = {
      key: `review-context-${now}`,
      from: 'assistant' as const,
      versions: [
        { id: `review-context-${now}-v1`, content: buildContextSummaryMessage(context) },
      ],
      createdAt: now,
      status: 'complete' as const,
    }
    main.updateMessages((prev) => {
      const existingKeys = new Set(prev.map((m) => m.key))
      // 已并入过同 scope 上下文摘要时不再重复追加（幂等）
      if (prev.some((m) => m.key.startsWith('review-context-'))) {
        return [...prev, ...messages.filter((m) => !existingKeys.has(m.key))]
      }
      return [contextMsg, ...prev, ...messages.filter((m) => !existingKeys.has(m.key))]
    })
    stores.chat.getState().clearMessages()
    stores.run.getState().reset()
    ai.reset()
    // 预填指令由 ai-chat 整页按 URL 契约生成（§3.7 reviewTask/reviewCase）
    void navigate({
      to: '/ai-chat',
      search: {
        reviewTask: String(taskId),
        reviewCase: caseId,
      },
    })
  }

  /** 供应商/模型切换写入有界会话 config（下一次 run 下发；与 /ai-chat 同口径） */
  const handleSelectProvider = (providerId: string) => {
    const chat = stores.chat.getState()
    chat.updateConfig('providerId', providerId)
    // 换供应商后清空模型：由新供应商的默认模型生效，避免沿用上一家的模型名
    chat.updateConfig('modelId', undefined)
  }
  const handleSelectModel = (modelId: string) => {
    stores.chat.getState().updateConfig('modelId', modelId)
  }
  const handleClearMessages = () => {
    handleEditOpenChange(false)
    resetChat()
    stores.chat.getState().clearMessages()
  }

  return {
    config,
    messages,
    draftText,
    setDraftText,
    providerManagerOpen,
    setProviderManagerOpen,
    contextQuery,
    ai,
    isGenerating,
    editingMessageKey,
    handleSendMessage,
    handleRegenerateMessage,
    handleEditMessage,
    handleEditPromptMessage,
    handleEditOpenChange,
    applyEdit,
    handleDeleteMessage,
    handleUndoMessage,
    stopGeneration,
    canSave,
    handleSave,
    handleAskQuick,
    expandToAiChat,
    handleSelectProvider,
    handleSelectModel,
    handleClearMessages,
  }
}

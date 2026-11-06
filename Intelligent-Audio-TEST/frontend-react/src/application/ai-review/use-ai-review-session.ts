/**
 * 复核会话编排 hook（application/ai-review，19 规范 §5.2/§5.4/§5.9，INT-1064）。
 * 灵犀Agent 复核会话（内嵌 Dialog）：复用 ai-chat 会话引擎（模型/供应商切换 + 消息渲染 +
 * 流式/追问），但**独立会话 scope**——数据存 agentReviewSessionStore（键
 * `iatp:ai-chat:v1:review:{taskId}:{caseId}`），不写入全局主会话；关闭即释放。
 * 打开时预填复核上下文（§5.3：首条 assistant 摘要卡）+ 首条用户指令（预填可编辑）；
 * 多轮追问 →「保存复核结论」落位 ai_reviews（真实端点）→ 采纳/驳回闭环（§5.5）。
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'

import { useAiChatSession } from '@/infrastructure/stores/aiChatSessionStore'
import {
  agentReviewSessionKey,
  useAgentReviewSessionStore,
} from '@/infrastructure/stores/agentReviewSessionStore'
import { useLlmProviders } from '@/features/ai-chat/hooks/use-llm-providers'
import { useChatHandler } from '@/features/ai-chat/hooks/use-chat-handler'
import { useChatConversation } from '@/features/ai-chat/hooks/use-chat-conversation'
import { DEFAULT_CONFIG } from '@/features/ai-chat/constants'

import { useAiReview } from '@/application/ai-review/use-ai-review'
import { useAiReviewContext } from '@/application/ai-review/use-ai-review-context'
import {
  buildContextSummaryMessage,
  buildReviewSystemPrompt,
  REVIEW_INITIAL_PROMPT,
} from '@/features/ai-review/constants'

export function useAiReviewSession({
  taskId,
  caseId,
  open,
  dimensionIds,
}: {
  taskId: number
  caseId: string
  open: boolean
  /** INT-1279：用例评估维度 id（保存复核结论显式传 dimension_ids，真实库无 LLM 判分维度时不 400） */
  dimensionIds?: number[]
}) {
  const navigate = useNavigate()
  const scopeKey = agentReviewSessionKey(taskId, caseId)
  const session = useAgentReviewSessionStore((s) => s.sessions[scopeKey])
  const config = session?.config ?? DEFAULT_CONFIG
  const messages = session?.messages ?? []
  const updateMessages = useAgentReviewSessionStore((s) => s.updateMessages)
  const updateConfig = useAgentReviewSessionStore((s) => s.updateConfig)
  const resetSession = useAgentReviewSessionStore((s) => s.resetSession)

  const {
    providers,
    addProvider,
    updateProvider,
    removeProvider,
    setDefaultProvider,
    defaultProvider,
    testConnection,
    fetchModels,
  } = useLlmProviders()
  const [providerManagerOpen, setProviderManagerOpen] = useState(false)
  const [draftText, setDraftText] = useState('')

  const contextQuery = useAiReviewContext(taskId, caseId, open)
  const ai = useAiReview(taskId, caseId)
  const context = contextQuery.context

  /** 当前会话供应商（config.providerId 命中或默认；§3.11 Demo 直连驱动对话） */
  const currentProvider =
    providers.find((p) => p.id === config.providerId) ??
    defaultProvider ??
    null

  /** 打开时重置状态机 + 每次打开为全新有界会话（§5.2 关闭即释放；scope 独立不残留）。
   * 必须先于配置即用 effect：打开瞬间清空该 scope，再由配置 effect 落位模型/供应商。 */
  const wasOpenRef = useRef(open)
  useEffect(() => {
    if (open && !wasOpenRef.current) {
      resetSession(taskId, caseId)
      ai.reset()
      setDraftText('')
    }
    wasOpenRef.current = open
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, taskId, caseId])

  /** 配置即用（§3.11/INT-1032 走查口径）：供应商带模型而会话未选模型/所选模型已不在
   * 清单时自动落首个模型——与 /ai-chat 整页同口径。仅在会话打开且 scope 就绪后生效。 */
  useEffect(() => {
    if (!open || !caseId) return
    if (!currentProvider) return
    const modelValid = currentProvider.models.includes(config.modelId ?? '')
    if (currentProvider.models.length > 0 && !modelValid) {
      updateConfig(taskId, caseId, 'providerId', currentProvider.id)
      updateConfig(taskId, caseId, 'modelId', currentProvider.models[0])
    }
  }, [currentProvider, config.modelId, taskId, caseId, updateConfig, open])

  const { sendChat, stopGeneration, isGenerating } = useChatHandler({
    config,
    provider: currentProvider,
    messages,
    // §5.3 复核上下文作为系统提示注入（首条 assistant 摘要卡由 AiReviewContextCard 结构化渲染）
    systemPrompt: context ? buildReviewSystemPrompt(context) : undefined,
    onMessageUpdate: (updater) => updateMessages(taskId, caseId, updater),
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
    updateMessages: (updater) => updateMessages(taskId, caseId, updater),
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
    resetSession(taskId, caseId)
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

  const handleSelectProvider = (providerId: string) => {
    updateConfig(taskId, caseId, 'providerId', providerId)
  }
  const handleSelectModel = (providerId: string, modelId: string) => {
    updateConfig(taskId, caseId, 'providerId', providerId)
    updateConfig(taskId, caseId, 'modelId', modelId)
  }
  const handleClearMessages = () => {
    handleEditOpenChange(false)
    updateMessages(taskId, caseId, () => [])
  }

  return {
    config,
    messages,
    draftText,
    setDraftText,
    providers,
    addProvider,
    updateProvider,
    removeProvider,
    setDefaultProvider,
    testConnection,
    fetchModels,
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

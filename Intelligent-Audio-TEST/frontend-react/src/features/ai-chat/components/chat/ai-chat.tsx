/**
 * 会话流装配（interfaces 层 ai-chat/chat；08_AI对话页.md §3.4 照 newAPI playground-chat）：
 * Conversation 粘底滚动 + 24 条历史截断 + 空态/加载态；每条消息编排内容/操作/编辑器。
 */
import { useEffect, useState } from 'react'

import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from '@/components/ai-elements/conversation'
import { Loader } from '@/components/ai-elements/loader'
import { Message } from '@/components/ai-elements/message'

import {
  getChatMessageRenderState,
  getCurrentMessageContent,
  getEditingMessageContent,
  getMessageAlignment,
  countLatestAssistantToolCalls,
} from '@/features/ai-chat/lib/message'
import {
  AGENT_RUN_PHASE_COPY,
  EMPTY_STATE_COPY,
  MAX_RENDERED_HISTORY_MESSAGES,
} from '@/features/ai-chat/constants'
import {
  AGENT_RUN_PHASE,
  type AgentRunPhase,
} from '@/application/agent/use-agent-run'
import {
  countTimelineToolCalls,
  type AgentTimelineEntry,
} from '@/application/agent/agent-timeline'
import {
  isPendingApprovalStatus,
  isTerminalRunStatus,
  type AgentApproval,
  type AgentApprovalDecision,
  type AgentAutoPause,
  type AgentAutoProgress,
  type AgentRun,
  type AgentRunPausePolicy,
} from '@/domain/models/agent'
import type { ChatMessage } from '@/domain/models/aiChat'

import { AiChatEmptyState } from './ai-chat-empty-state'
import { AiChatMessageContent } from '@/features/ai-chat/components/message/message-content'
import { MessageActions } from '@/features/ai-chat/components/message/message-actions'
import { MessageEditor } from '@/features/ai-chat/components/message/message-editor'
import { ApprovalPanel } from '@/features/ai-chat/components/approval/approval-panel'
import { AutoProgressPanel } from '@/features/ai-chat/components/auto-mode/auto-progress-panel'
import { RunTimeline } from '@/features/ai-chat/components/run-timeline/run-timeline'

type AiChatProps = {
  messages: ChatMessage[]
  isLoadingMessages?: boolean
  onRegenerateMessage?: (message: ChatMessage) => void
  onEditMessage?: (message: ChatMessage) => void
  onDeleteMessage?: (message: ChatMessage) => void
  onUndoMessage?: (message: ChatMessage) => void
  /** 空态 starter：回填输入框不自动发送（§3.3） */
  onFillPrompt?: (prompt: string) => void
  /** 错误消息操作组「编辑后重发」定位（§3.4） */
  onEditPromptMessage?: (message: ChatMessage) => void
  isGenerating?: boolean
  editingKey?: string | null
  onCancelEdit?: (open: boolean) => void
  onSaveEdit?: (newContent: string) => void
  onSaveEditAndSubmit?: (newContent: string) => void
  /** 平台 Agent run 阶段（INT-2457：准备 / 重连 / 取消在会话区顶部提示） */
  runPhase?: AgentRunPhase
  /** 写操作审批卡（INT-2472）：本 run 的审批单 + 决策回调 */
  approvals?: AgentApproval[]
  approvalsLoading?: boolean
  approvalsError?: string | null
  /** 决策请求在途的审批单 id（按钮防重复） */
  decidingApprovalIds?: string[]
  onDecideApproval?: (
    approvalId: string,
    decision: AgentApprovalDecision,
    /** DESTRUCTIVE 二次确认：仅确认后带 true（后端 INT-2467 契约） */
    confirm?: boolean
  ) => Promise<string | null>
  onRetryApprovals?: () => void
  /** Run 时间线（事件流有序投影）与 run 快照（预算消耗） */
  timeline?: AgentTimelineEntry[]
  run?: AgentRun | null
  /** Auto 进度 / 暂停（INT-2474；非 Auto run 为 null，面板不渲染） */
  autoProgress?: AgentAutoProgress | null
  autoPause?: AgentAutoPause | null
  autoPausePolicy?: AgentRunPausePolicy | null
  /** 「继续」在途 / 取消在途 */
  resumingAuto?: boolean
  isCancelling?: boolean
  /** Auto 暂停后继续；结束运行（取消当前 run） */
  onResumeAuto?: () => void
  onStopAuto?: () => void
  /** run 级错误（事件流失败 / 继续失败提示；Auto 面板内展示） */
  runError?: string | null
  /** 全局 Agent 工作台浮窗紧凑形态（§3.1B：高度受限更紧凑间距） */
  compact?: boolean
}

export function AiChat({
  messages,
  isLoadingMessages = false,
  onRegenerateMessage,
  onEditMessage,
  onDeleteMessage,
  onUndoMessage,
  onFillPrompt,
  onEditPromptMessage,
  isGenerating = false,
  editingKey,
  onCancelEdit,
  onSaveEdit,
  onSaveEditAndSubmit,
  runPhase,
  approvals = [],
  approvalsLoading = false,
  approvalsError = null,
  decidingApprovalIds = [],
  onDecideApproval,
  onRetryApprovals,
  timeline = [],
  run = null,
  autoProgress = null,
  autoPause = null,
  autoPausePolicy = null,
  resumingAuto = false,
  isCancelling = false,
  onResumeAuto,
  onStopAuto,
  runError = null,
  compact = false,
}: AiChatProps) {
  const [editText, setEditText] = useState('')
  const [originalText, setOriginalText] = useState('')
  const [sourceMessageKeys, setSourceMessageKeys] = useState<
    ReadonlySet<string>
  >(() => new Set())

  const visibleMessageOffset = Math.max(
    0,
    messages.length - MAX_RENDERED_HISTORY_MESSAGES
  )
  const visibleMessages = messages.slice(visibleMessageOffset)

  /**
   * 审批面板「工具调用」计数（P3-1）：时间线是当前页面会话的事件投影，刷新后为空，
   * 此时改用最后一条 assistant 气泡里已落的工具卡，避免与「待审批 1」不一致。
   */
  const toolCallCount =
    timeline.length > 0
      ? countTimelineToolCalls(timeline)
      : countLatestAssistantToolCalls(messages)
  /** run 已收口：已批准审批卡不再展示「将在服务端执行」的将来时（P3-5） */
  const runFinished = run !== null && isTerminalRunStatus(run.status)
  /** Auto 面板的待审批计数（与审批卡同源：同一份 approvals） */
  const pendingApprovalCount = approvals.filter((approval) =>
    isPendingApprovalStatus(approval.status)
  ).length

  const handleToggleMessageSource = (message: ChatMessage) => {
    setSourceMessageKeys((currentKeys) => {
      const nextKeys = new Set(currentKeys)
      if (nextKeys.has(message.key)) {
        nextKeys.delete(message.key)
      } else {
        nextKeys.add(message.key)
      }
      return nextKeys
    })
  }

  useEffect(() => {
    if (!editingKey) return
    const content = getEditingMessageContent(messages, editingKey)
    setEditText(content)
    setOriginalText(content)
  }, [editingKey, messages])

  let chatContent = visibleMessages.map((message, visibleMessageIndex) => {
    const messageIndex = visibleMessageOffset + visibleMessageIndex
    const { alwaysShowActions, isEditing } = getChatMessageRenderState(
      messages,
      message,
      messageIndex,
      editingKey ?? null
    )
    const alignment = getMessageAlignment(message)
    const isSourceVisible = sourceMessageKeys.has(message.key)
    const content = getCurrentMessageContent(message)

    return (
      <Message
        className='group flex-row-reverse py-2.5'
        from={message.from}
        key={message.key}
      >
        <div className='basis-full min-w-0 flex-1'>
          {isEditing ? (
            <MessageEditor
              editText={editText}
              message={message}
              onCancelEdit={onCancelEdit ?? (() => undefined)}
              onEditTextChange={setEditText}
              onSaveEdit={onSaveEdit ?? (() => undefined)}
              onSaveEditAndSubmit={onSaveEditAndSubmit ?? (() => undefined)}
              originalText={originalText}
            />
          ) : (
            <AiChatMessageContent
              actions={
                <MessageActions
                  alwaysVisible={alwaysShowActions}
                  isGenerating={isGenerating}
                  isSourceVisible={isSourceVisible}
                  message={message}
                  onDelete={onDeleteMessage}
                  onEdit={onEditMessage}
                  onRegenerate={onRegenerateMessage}
                  onToggleSource={handleToggleMessageSource}
                  onUndo={onUndoMessage}
                />
              }
              alignment={alignment}
              errorActions={undefined}
              isSourceVisible={isSourceVisible}
              message={message}
              onDeleteMessage={onDeleteMessage}
              onEditPromptMessage={onEditPromptMessage}
              onRetryMessage={onRegenerateMessage}
              versionContent={content}
            />
          )}
        </div>
      </Message>
    )
  })

  if (visibleMessages.length === 0 && onFillPrompt) {
    chatContent = [
      <AiChatEmptyState
        compact={compact}
        key='empty'
        onFillPrompt={onFillPrompt}
      />,
    ]
  }

  /**
   * SSE 重连 / 取消 / 准备 / 审批等待提示（§12.2：只提示不改消息）。
   * Auto 暂停（无待审批提案）时不显示「等待你审批写操作」——暂停面板已给准确口径，
   * 这里再提示会让用户以为卡在审批上。
   */
  const autoPausedWithoutApprovals = autoPause !== null && pendingApprovalCount === 0
  const runPhaseHint =
    runPhase === AGENT_RUN_PHASE.RECONNECTING
      ? AGENT_RUN_PHASE_COPY.reconnecting
      : runPhase === AGENT_RUN_PHASE.CANCELLING
        ? AGENT_RUN_PHASE_COPY.cancelling
        : runPhase === AGENT_RUN_PHASE.PREPARING
          ? AGENT_RUN_PHASE_COPY.preparing
          : runPhase === AGENT_RUN_PHASE.WAITING_APPROVAL &&
              !autoPausedWithoutApprovals
            ? AGENT_RUN_PHASE_COPY.waitingApproval
            : null

  if (isLoadingMessages) {
    chatContent = [
      <div
        className='text-muted-foreground flex min-h-[min(520px,calc(100svh-18rem))] items-center justify-center gap-2 text-sm'
        key='loading'
      >
        <Loader />
        <span>{EMPTY_STATE_COPY.loading}</span>
      </div>,
    ]
  }

  return (
    <Conversation>
      <ConversationContent className='p-0'>
        <div
          className={
            compact
              ? 'mx-auto w-full max-w-full px-3 py-2'
              : 'mx-auto w-full max-w-4xl px-4 py-4'
          }
        >
          {runPhaseHint && (
            <div
              className='border-border/60 bg-muted/30 text-muted-foreground mb-3 flex items-center gap-2 rounded-lg border px-3 py-2 text-xs'
              data-agent-run-phase={runPhase}
              role='status'
            >
              <Loader />
              <span>{runPhaseHint}</span>
            </div>
          )}
          {chatContent}
          {/* Auto 进度 / 暂停 / 终态（INT-2474 §9.4）：只在 Auto run 上渲染 */}
          <AutoProgressPanel
            error={runError}
            onResume={onResumeAuto}
            onStop={onStopAuto}
            pause={autoPause}
            pausePolicy={autoPausePolicy}
            pendingApprovalCount={pendingApprovalCount}
            progress={autoProgress}
            resuming={resumingAuto}
            run={run}
            stopping={isCancelling}
          />
          {/* 写操作审批卡（§12.2）：按步骤分组展示提案 / diff / 风险 / 过期；逐条决策 */}
          {onDecideApproval && (
            <ApprovalPanel
              approvals={approvals}
              decidingApprovalIds={decidingApprovalIds}
              error={approvalsError}
              loading={approvalsLoading}
              onDecide={onDecideApproval}
              onRetry={onRetryApprovals}
              runFinished={runFinished}
              toolCallCount={toolCallCount}
            />
          )}
          {/* Run 时间线（§12.2）：事件 sequence 有序投影，默认折叠 */}
          <RunTimeline entries={timeline} run={run} />
        </div>
      </ConversationContent>
      <ConversationScrollButton />
    </Conversation>
  )
}

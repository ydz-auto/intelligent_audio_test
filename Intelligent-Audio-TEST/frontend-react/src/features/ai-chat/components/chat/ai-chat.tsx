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
import type { ChatMessage } from '@/domain/models/aiChat'

import { AiChatEmptyState } from './ai-chat-empty-state'
import { AiChatMessageContent } from '@/features/ai-chat/components/message/message-content'
import { MessageActions } from '@/features/ai-chat/components/message/message-actions'
import { MessageEditor } from '@/features/ai-chat/components/message/message-editor'

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

  /** SSE 重连 / 取消 / 准备态提示（§12.2「SSE 重连不重复渲染」：只提示不改消息） */
  const runPhaseHint =
    runPhase === AGENT_RUN_PHASE.RECONNECTING
      ? AGENT_RUN_PHASE_COPY.reconnecting
      : runPhase === AGENT_RUN_PHASE.CANCELLING
        ? AGENT_RUN_PHASE_COPY.cancelling
        : runPhase === AGENT_RUN_PHASE.PREPARING
          ? AGENT_RUN_PHASE_COPY.preparing
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
        </div>
      </ConversationContent>
      <ConversationScrollButton />
    </Conversation>
  )
}

/**
 * 消息内容编排（interfaces 层 ai-chat/message；08_AI对话页.md §3.4 照 newAPI
 * playground-message-content）：思考过程 → 工具卡 → 文档变更卡 → 正文（流式）→
 * 数据来源 → 元数据 → 操作组；源码视图用 CodeBlock 替换正文。
 */
import type { ReactNode } from 'react'

import { CodeBlock } from '@/components/ai-elements/code-block'
import { Loader } from '@/components/ai-elements/loader'
import { MessageContent } from '@/components/ai-elements/message'
import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
} from '@/components/ai-elements/reasoning'
import { Response } from '@/components/ai-elements/response'
import { Shimmer } from '@/components/ai-elements/shimmer'
import { cn } from '@/lib/utils'

import { MESSAGE_STATUS } from '@/features/ai-chat/constants'
import {
  getMessageAlignmentClass,
  isErrorMessage,
} from '@/features/ai-chat/lib/message'
import type { ChatMessage } from '@/domain/models/aiChat'

import { DataSources } from './data-sources'
import { DocumentChangeCard } from './document-change-card'
import { MessageError } from './message-error'
import { MessageMetadata } from './message-metadata'
import { ToolCallCard } from './tool-call-card'

type AiChatMessageContentProps = {
  actions?: ReactNode
  alignment: 'right' | 'left'
  errorActions?: ReactNode
  isSourceVisible?: boolean
  message: ChatMessage
  versionContent: string
  /** 错误消息操作组（§3.4：重试 / 编辑后重发 / 删除） */
  onRetryMessage?: (message: ChatMessage) => void
  onEditPromptMessage?: (message: ChatMessage) => void
  onDeleteMessage?: (message: ChatMessage) => void
}

export function AiChatMessageContent({
  actions,
  alignment,
  errorActions,
  isSourceVisible = false,
  message,
  versionContent,
  onRetryMessage,
  onEditPromptMessage,
  onDeleteMessage,
}: AiChatMessageContentProps) {
  const isUser = message.from === 'user'
  const isError = isErrorMessage(message)
  const isMessageFinal =
    message.status !== MESSAGE_STATUS.LOADING &&
    message.status !== MESSAGE_STATUS.STREAMING
  const showLoader = message.status === MESSAGE_STATUS.LOADING
  const hasReasoning =
    Boolean(message.reasoning) &&
    (Boolean(message.reasoning?.content) || message.isReasoningStreaming)
  const reasoningContent = message.reasoning?.content ?? ''
  const hasSources = (message.sourceRefs?.length ?? 0) > 0
  const hasToolCalls = (message.toolCalls?.length ?? 0) > 0
  const hasDocumentChanges = (message.documentChanges?.length ?? 0) > 0

  // user 消息：气泡内纯文本
  if (isUser) {
    return (
      <div
        className={cn(
          'flex w-full min-w-0 flex-col',
          getMessageAlignmentClass(alignment)
        )}
      >
        <div className='whitespace-pre-wrap text-left'>
          {versionContent}
        </div>
      </div>
    )
  }

  return (
    <div
      className={cn(
        'flex w-full min-w-0 flex-col',
        getMessageAlignmentClass(alignment)
      )}
    >
      {hasSources && (
        <DataSources refs={message.sourceRefs ?? []} />
      )}

      {hasReasoning && (
        <Reasoning
          defaultOpen={message.isReasoningStreaming}
          duration={message.reasoning?.duration ?? 0}
          isStreaming={message.isReasoningStreaming}
        >
          <ReasoningTrigger
            duration={message.reasoning?.duration ?? 0}
            isStreaming={message.isReasoningStreaming}
          />
          <ReasoningContent>{reasoningContent}</ReasoningContent>
        </Reasoning>
      )}

      {hasToolCalls &&
        message.toolCalls?.map((call) => (
          <ToolCallCard call={call} key={call.id} />
        ))}

      {hasDocumentChanges &&
        message.documentChanges?.map((change) => (
          <DocumentChangeCard change={change} key={change.documentId} />
        ))}

      {showLoader && (
        <div className='flex items-center gap-2 py-2'>
          <Loader />
          <Shimmer className='text-sm' duration={1}>
            正在回复...
          </Shimmer>
        </div>
      )}

      {isError && (
        <>
          <MessageError
            detail={versionContent}
            disabled={!isMessageFinal}
            errorCode={message.errorCode}
            onDelete={onDeleteMessage ? () => onDeleteMessage(message) : undefined}
            onEditPrompt={
              onEditPromptMessage ? () => onEditPromptMessage(message) : undefined
            }
            onRetry={onRetryMessage ? () => onRetryMessage(message) : undefined}
          />
          <MessageMetadata
            durationMs={message.durationMs}
            timestamp={message.completedAt ?? message.createdAt}
          />
          {errorActions}
        </>
      )}

      {!isError && !showLoader && (
        <>
          {isSourceVisible ? (
            <CodeBlock
              className='my-0 group-[.is-assistant]:w-full group-[.is-assistant]:max-w-[78ch]'
              code={versionContent}
              collapsedLines={24}
              language='markdown'
              maxExpandedLines={48}
              title='原始回复'
            />
          ) : (
            <MessageContent variant='flat'>
              <Response final={isMessageFinal}>{versionContent}</Response>
            </MessageContent>
          )}
          <MessageMetadata
            durationMs={message.durationMs}
            timestamp={message.completedAt ?? message.createdAt}
          />
          {actions}
        </>
      )}
    </div>
  )
}

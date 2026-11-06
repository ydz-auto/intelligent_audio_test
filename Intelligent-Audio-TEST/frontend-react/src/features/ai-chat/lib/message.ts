/**
 * 消息纯函数（interfaces 层 lib/message；照 newAPI lib/message 平移）。
 * 对齐/渲染态/编辑态/错误定位——视觉稿不接 Agent 后端，状态机先行版式。
 */
import type { ChatMessage } from '@/domain/models/aiChat'
import { MESSAGE_STATUS } from '@/features/ai-chat/constants'

export type MessageLayoutMode = 'alternating' | 'left'

/** 交替对齐：user 右 / assistant 左（§3.4 照 playground getMessageAlignment 语义） */
export function getMessageAlignment(
  message: ChatMessage,
  mode: MessageLayoutMode = 'alternating'
): 'right' | 'left' {
  if (mode === 'left') return 'left'
  return message.from === 'user' ? 'right' : 'left'
}

export function getMessageAlignmentClass(
  alignment: 'right' | 'left'
): string {
  return alignment === 'right'
    ? 'items-end text-right'
    : 'items-start text-left'
}

export function isErrorMessage(message: ChatMessage): boolean {
  return message.status === MESSAGE_STATUS.ERROR
}

export function isStreamingMessage(message: ChatMessage): boolean {
  return (
    message.status === MESSAGE_STATUS.STREAMING ||
    message.status === MESSAGE_STATUS.LOADING
  )
}

/** 当前可见内容 = 最新版本（编辑器保存产生新版本） */
export function getCurrentMessageContent(message: ChatMessage): string {
  const lastVersion = message.versions[message.versions.length - 1]
  return lastVersion?.content ?? ''
}

/** 上一条 user 消息（错误操作「编辑」定位用） */
export function getPreviousUserMessage(
  messages: ChatMessage[],
  index: number
): ChatMessage | null {
  for (let i = index - 1; i >= 0; i -= 1) {
    if (messages[i].from === 'user') return messages[i]
  }
  return null
}

/** 渲染态：该条是否正在编辑、操作组是否恒显（最后一条 assistant 恒显） */
export function getChatMessageRenderState(
  messages: ChatMessage[],
  message: ChatMessage,
  index: number,
  editingKey: string | null
): { isEditing: boolean; alwaysShowActions: boolean } {
  const isEditing = editingKey === message.key
  const isLastAssistant =
    message.from === 'assistant' && index === messages.length - 1
  return { isEditing, alwaysShowActions: isLastAssistant }
}

export function getEditingMessageContent(
  messages: ChatMessage[],
  editingKey: string | null
): string {
  if (!editingKey) return ''
  const target = messages.find((message) => message.key === editingKey)
  return target ? getCurrentMessageContent(target) : ''
}

/** 格式化时长（元数据「响应时间：{n}」） */
export function formatDuration(durationMs: number): string {
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`
  return `${(durationMs / 1000).toFixed(1)}s`
}

/** 格式化时间 HH:mm:ss（元数据） */
export function formatMessageTime(timestamp: number): string {
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(timestamp))
}

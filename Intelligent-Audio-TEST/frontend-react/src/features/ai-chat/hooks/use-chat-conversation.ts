/**
 * AI 对话会话编排（interfaces 层 hooks；照 newAPI use-playground-conversation 平移）：
 * 发送 / 重新生成（截断重建）/ 编辑提交 / 删除 / 撤销修改（占位）。
 */
import { useCallback, useState } from 'react'
import { toast } from 'sonner'

import type { ChatMessage } from '@/domain/models/aiChat'
import {
  getCurrentMessageContent,
  getPreviousUserMessage,
} from '@/features/ai-chat/lib/message'

type UpdateMessagesFn = (updater: (prev: ChatMessage[]) => ChatMessage[]) => void

export function useChatConversation({
  messages,
  updateMessages,
  sendChat,
}: {
  messages: ChatMessage[]
  updateMessages: UpdateMessagesFn
  sendChat: (text: string) => void
}) {
  const [editingMessageKey, setEditingMessageKey] = useState<string | null>(null)

  const handleSendMessage = useCallback(
    (text: string) => {
      sendChat(text)
    },
    [sendChat]
  )

  /** 重新生成：截断到该条 assistant 的上一条 user 消息并重发（照 createRegeneratedMessages） */
  const handleRegenerateMessage = useCallback(
    (message: ChatMessage) => {
      const index = messages.findIndex((item) => item.key === message.key)
      if (index < 0) return
      const previousUser = getPreviousUserMessage(messages, index)
      if (!previousUser) return
      const text = getCurrentMessageContent(previousUser)
      updateMessages((prev) => prev.slice(0, index))
      sendChat(text)
    },
    [messages, sendChat, updateMessages]
  )

  const handleEditMessage = useCallback(
    (message: ChatMessage) => {
      setEditingMessageKey(message.key)
    },
    []
  )

  const handleEditOpenChange = useCallback((open: boolean) => {
    if (!open) setEditingMessageKey(null)
  }, [])

  /** 编辑提交：保存新版本；submit=true 时保存并重发 */
  const applyEdit = useCallback(
    (newContent: string, submit: boolean) => {
      if (!editingMessageKey) return
      const target = messages.find(
        (message) => message.key === editingMessageKey
      )
      if (!target) return

      updateMessages((prev) =>
        prev.map((message) => {
          if (message.key !== editingMessageKey) return message
          return {
            ...message,
            versions: [
              ...message.versions,
              {
                id: `${message.key}-v${message.versions.length + 1}`,
                content: newContent,
              },
            ],
          }
        })
      )
      setEditingMessageKey(null)

      if (submit) {
        const previousContent = getCurrentMessageContent(target)
        if (previousContent !== newContent) {
          sendChat(newContent)
        }
      }
    },
    [editingMessageKey, messages, sendChat, updateMessages]
  )

  const handleDeleteMessage = useCallback(
    (message: ChatMessage) => {
      updateMessages((prev) =>
        prev.filter((item) => item.key !== message.key)
      )
    },
    [updateMessages]
  )

  /** 撤销修改（studio_restore_version，恢复产生新版本不覆盖；待后端立项） */
  const handleUndoMessage = useCallback(
    (_message: ChatMessage) => {
      toast.info('撤销修改（studio_restore_version）待后端立项', {
        description: '恢复历史版本将产生新版本，不覆盖当前文档。',
      })
    },
    []
  )

  return {
    editingMessageKey,
    handleSendMessage,
    handleRegenerateMessage,
    handleEditMessage,
    handleEditOpenChange,
    applyEdit,
    handleDeleteMessage,
    handleUndoMessage,
  }
}

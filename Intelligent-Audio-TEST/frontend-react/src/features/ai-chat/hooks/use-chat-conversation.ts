/**
 * AI 对话会话编排（interfaces 层 hooks；照 newAPI use-playground-conversation 平移）：
 * 发送 / 重新生成（截断重建）/ 编辑提交 / 删除 / 撤销修改（占位）。
 */
import { useCallback, useState } from 'react'
import { toast } from 'sonner'

import type { ChatMessage } from '@/domain/models/aiChat'
import type { SendChatOptions } from '@/features/ai-chat/hooks/use-chat-handler'
import {
  getCurrentMessageContent,
  getPreviousUserMessage,
} from '@/features/ai-chat/lib/message'

type UpdateMessagesFn = (updater: (prev: ChatMessage[]) => ChatMessage[]) => void

export function useChatConversation({
  messages,
  updateMessages,
  sendChat,
  deletePersist,
}: {
  messages: ChatMessage[]
  updateMessages: UpdateMessagesFn
  sendChat: (text: string, options?: SendChatOptions) => void
  /** 删除持久化（平台会话：服务端隐藏集合；缺省只删本地） */
  deletePersist?: (message: ChatMessage) => Promise<void>
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
      const previousUserIndex = messages.findIndex(
        (item) => item.key === previousUser.key
      )
      if (previousUserIndex < 0) return
      const text = getCurrentMessageContent(previousUser)
      // 重新生成=截断重建（§3.4）：UI 截断到该条 assistant 的上一条 user 消息；
      // 请求体用截断后历史（不含旧 assistant 回复与重复指令）构造——sendChat 支持 history
      // override，且不追加新 user 消息（原指令已在截断数组内）。
      updateMessages((prev) => prev.slice(0, index))
      sendChat(text, {
        historyMessages: messages.slice(0, previousUserIndex),
        appendUserMessage: false,
      })
    },
    [messages, sendChat, updateMessages]
  )

  const handleEditMessage = useCallback(
    (message: ChatMessage) => {
      setEditingMessageKey(message.key)
    },
    []
  )

  /** 错误消息「编辑后重发」：定位到上一条 user 消息进入编辑态（§3.4，照 playground error 操作语义） */
  const handleEditPromptMessage = useCallback(
    (message: ChatMessage) => {
      const index = messages.findIndex((item) => item.key === message.key)
      if (index < 0) return
      const previousUser = getPreviousUserMessage(messages, index)
      if (!previousUser) return
      setEditingMessageKey(previousUser.key)
    },
    [messages]
  )

  const handleEditOpenChange = useCallback((open: boolean) => {
    if (!open) setEditingMessageKey(null)
  }, [])

  /**
   * 编辑提交：保存新版本；submit=true 时保存并重发。
   *
   * 重发只复用被编辑的这条 user 消息：截断其后的旧回答 / 错误气泡，并以
   * ``appendUserMessage: false`` 发送 —— 否则界面会多出一条同样的用户输入
   * （编辑前的那条 + 新追加的一条），看起来像「用户输入被重复发送」。
   */
  const applyEdit = useCallback(
    (newContent: string, submit: boolean) => {
      if (!editingMessageKey) return
      const index = messages.findIndex(
        (message) => message.key === editingMessageKey
      )
      if (index < 0) return
      const target = messages[index]
      const previousContent = getCurrentMessageContent(target)
      const resend = submit && previousContent !== newContent

      updateMessages((prev) => {
        const next = prev.map((message) => {
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
        // 重发 = 截断重建：编辑的 user 消息之后是旧回答 / 错误气泡，不再保留
        return resend ? next.slice(0, index + 1) : next
      })
      setEditingMessageKey(null)

      if (resend) {
        sendChat(newContent, {
          historyMessages: messages.slice(0, index),
          appendUserMessage: false,
        })
      }
    },
    [editingMessageKey, messages, sendChat, updateMessages]
  )

  const handleDeleteMessage = useCallback(
    (message: ChatMessage) => {
      const remove = () =>
        updateMessages((prev) =>
          prev.filter((item) => item.key !== message.key)
        )
      if (!deletePersist) {
        remove()
        return
      }
      // 先落服务端隐藏集合再删本地：失败保留消息，避免「界面删了、刷新又回来」
      void deletePersist(message)
        .then(remove)
        .catch((err) => {
          toast.error(
            err instanceof Error && err.message
              ? err.message
              : '删除失败，请重试'
          )
        })
    },
    [deletePersist, updateMessages]
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
    handleEditPromptMessage,
    handleEditOpenChange,
    applyEdit,
    handleDeleteMessage,
    handleUndoMessage,
  }
}

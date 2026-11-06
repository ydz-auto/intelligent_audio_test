/**
 * use-chat-conversation 单测（INT-598 代码审计返修 P2-4）：
 * 重新生成=截断重建（§3.4）——UI 截断到上一条 user 消息，请求体用截断后历史构造
 * （sendChat 收 historyMessages override + appendUserMessage=false，不残留旧 assistant 回复、
 * 不重复追加 user 指令）。
 */
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ChatMessage } from '@/domain/models/aiChat'
import { MESSAGE_STATUS } from '@/features/ai-chat/constants'
import { useChatConversation } from '@/features/ai-chat/hooks/use-chat-conversation'
import type { SendChatOptions } from '@/features/ai-chat/hooks/use-chat-handler'

function makeMessage(
  key: string,
  from: 'user' | 'assistant',
  content: string,
  status = MESSAGE_STATUS.COMPLETE
): ChatMessage {
  return {
    key,
    from,
    versions: [{ id: `${key}-v1`, content }],
    status,
    createdAt: Date.now(),
  }
}

describe('useChatConversation（重新生成截断重建，P2-4 返修）', () => {
  it('重新生成：截断到上一条 user 消息，sendChat 收截断后历史 + 不追加新 user 消息', () => {
    const messages = [
      makeMessage('u1', 'user', '第一问'),
      makeMessage('a1', 'assistant', '第一答'),
      makeMessage('u2', 'user', '第二问'),
      makeMessage('a2', 'assistant', '旧第二答'),
    ]
    const sendChat = vi.fn()
    const updateMessages = vi.fn()
    const { result } = renderHook(() =>
      useChatConversation({ messages, updateMessages, sendChat })
    )

    act(() => {
      result.current.handleRegenerateMessage(messages[3])
    })

    // UI 截断到 a2 之前（保留 u2 指令，移除旧第二答）
    expect(updateMessages).toHaveBeenCalledWith(expect.any(Function))
    const truncateFn = updateMessages.mock.calls[0][0]
    expect(truncateFn(messages)).toEqual([...messages.slice(0, 3)])

    // 请求体历史 = 上一条 user 消息之前的全部（不含旧 assistant 回复与重复指令）
    expect(sendChat).toHaveBeenCalledWith('第二问', {
      historyMessages: [messages[0], messages[1]],
      appendUserMessage: false,
    } satisfies SendChatOptions)
  })

  it('重新生成：无上一条 user 消息时不动作', () => {
    const messages = [makeMessage('a0', 'assistant', '首条 assistant')]
    const sendChat = vi.fn()
    const updateMessages = vi.fn()
    const { result } = renderHook(() =>
      useChatConversation({ messages, updateMessages, sendChat })
    )

    act(() => {
      result.current.handleRegenerateMessage(messages[0])
    })

    expect(sendChat).not.toHaveBeenCalled()
    expect(updateMessages).not.toHaveBeenCalled()
  })
})

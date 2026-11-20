/**
 * 侧边会话上下文前缀：只带主对话最近若干条用户 / 助手消息，跳过进行中与失败消息。
 */
import { describe, expect, it } from 'vitest'

import { CHAT_MESSAGE_STATUS, type ChatMessage } from '@/domain/models/aiChat'
import { SIDE_CONTEXT_COPY } from '@/features/ai-chat/constants'
import { buildSideConversationContext } from '@/features/ai-chat/lib/context-prompt'

function message(
  index: number,
  from: 'user' | 'assistant',
  content: string,
  status: ChatMessage['status'] = CHAT_MESSAGE_STATUS.COMPLETE
): ChatMessage {
  return {
    key: `m-${index}`,
    from,
    versions: [{ id: `m-${index}-v1`, content }],
    createdAt: index,
    status,
  }
}

describe('buildSideConversationContext（侧边会话读主对话上下文）', () => {
  it('没有可带入的消息时返回 null（不注入空前缀）', () => {
    expect(buildSideConversationContext([])).toBeNull()
    expect(
      buildSideConversationContext([
        message(1, 'user', '   '),
        message(2, 'assistant', '生成中', CHAT_MESSAGE_STATUS.LOADING),
        message(3, 'assistant', '失败', CHAT_MESSAGE_STATUS.ERROR),
      ])
    ).toBeNull()
  })

  it('按角色拼接近况，丢弃进行中 / 失败消息', () => {
    const prefix = buildSideConversationContext([
      message(1, 'user', '帮我生成任务 #320 的报告'),
      message(2, 'assistant', '已生成，见报告 #426'),
      message(3, 'assistant', '生成中', CHAT_MESSAGE_STATUS.LOADING),
    ])

    expect(prefix).toContain('用户：帮我生成任务 #320 的报告')
    expect(prefix).toContain('助手：已生成，见报告 #426')
    expect(prefix).not.toContain('生成中')
    expect(prefix?.startsWith(SIDE_CONTEXT_COPY.preface)).toBe(true)
  })

  it('只保留最近 maxMessages 条，超出单条上限时截断并加省略号', () => {
    const long = 'x'.repeat(SIDE_CONTEXT_COPY.maxCharsPerMessage + 10)
    const messages = [
      message(0, 'user', '最早一条'),
      ...Array.from(
        { length: SIDE_CONTEXT_COPY.maxMessages },
        (_, index) => message(index + 1, 'user', `第 ${index + 1} 条`)
      ),
      message(99, 'assistant', long),
    ]

    const prefix = buildSideConversationContext(messages) ?? ''
    expect(prefix).not.toContain('最早一条')
    expect(prefix).toContain('助手：')
    expect(prefix).toContain('…')
    expect(prefix).not.toContain(long)
  })
})

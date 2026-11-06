/**
 * features/ai-chat/lib/message 纯函数测试（照 newAPI lib/message 平移语义：
 * 对齐/错误定位/编辑态/时长与时间格式化）。
 */
import { describe, expect, it } from 'vitest'

import {
  formatDuration,
  formatMessageTime,
  getChatMessageRenderState,
  getCurrentMessageContent,
  getEditingMessageContent,
  getMessageAlignment,
  getMessageAlignmentClass,
  getPreviousUserMessage,
  isErrorMessage,
  isStreamingMessage,
} from '@/features/ai-chat/lib/message'
import type { ChatMessage } from '@/domain/models/aiChat'

const userMessage: ChatMessage = {
  key: 'u1',
  from: 'user',
  versions: [{ id: 'v1', content: '帮我把最近的测试任务生成一份测试报告' }],
  status: 'complete',
}

const assistantMessage: ChatMessage = {
  key: 'a1',
  from: 'assistant',
  versions: [
    { id: 'v1', content: '第一版' },
    { id: 'v2', content: '第二版' },
  ],
  status: 'streaming',
  durationMs: 1520,
  createdAt: 0,
}

describe('getMessageAlignment', () => {
  it('交替模式 user 右、assistant 左', () => {
    expect(getMessageAlignment(userMessage)).toBe('right')
    expect(getMessageAlignment(assistantMessage)).toBe('left')
  })

  it('left 模式恒左', () => {
    expect(getMessageAlignment(userMessage, 'left')).toBe('left')
  })

  it('对齐类名映射', () => {
    expect(getMessageAlignmentClass('right')).toBe('items-end text-right')
    expect(getMessageAlignmentClass('left')).toBe('items-start text-left')
  })
})

describe('消息状态判定', () => {
  it('错误消息', () => {
    expect(
      isErrorMessage({ ...assistantMessage, status: 'error' })
    ).toBe(true)
    expect(isErrorMessage(userMessage)).toBe(false)
  })

  it('流式/加载消息', () => {
    expect(isStreamingMessage({ ...assistantMessage, status: 'streaming' })).toBe(
      true
    )
    expect(isStreamingMessage({ ...assistantMessage, status: 'loading' })).toBe(
      true
    )
    expect(isStreamingMessage({ ...assistantMessage, status: 'complete' })).toBe(
      false
    )
  })
})

describe('内容与编辑定位', () => {
  it('取最新版本作为当前内容', () => {
    expect(getCurrentMessageContent(assistantMessage)).toBe('第二版')
  })

  it('向前回溯上一条 user 消息', () => {
    const list = [assistantMessage, userMessage, assistantMessage]
    expect(getPreviousUserMessage(list, 2)?.key).toBe('u1')
    expect(getPreviousUserMessage(list, 0)).toBeNull()
  })

  it('渲染态：编辑中/末条 assistant 恒显操作组', () => {
    const list = [userMessage, assistantMessage]
    expect(
      getChatMessageRenderState(list, assistantMessage, 1, 'a1')
    ).toEqual({ isEditing: true, alwaysShowActions: true })
    expect(
      getChatMessageRenderState(list, userMessage, 0, 'a1')
    ).toEqual({ isEditing: false, alwaysShowActions: false })
  })

  it('编辑内容按 key 取当前版本，无 key 返回空串', () => {
    expect(getEditingMessageContent([userMessage], 'u1')).toBe(
      '帮我把最近的测试任务生成一份测试报告'
    )
    expect(getEditingMessageContent([userMessage], null)).toBe('')
    expect(getEditingMessageContent([userMessage], 'missing')).toBe('')
  })
})

describe('格式化', () => {
  it('时长毫秒/秒两级格式化', () => {
    expect(formatDuration(800)).toBe('800ms')
    expect(formatDuration(1520)).toBe('1.5s')
  })

  it('时间戳格式化为 HH:mm:ss（zh-CN）', () => {
    expect(formatMessageTime(0)).toMatch(/^\d{2}:\d{2}:\d{2}$/)
  })
})

/**
 * 灵犀Agent 本地存储工具测试（§3.7 上限/sanitize/envelope）。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import {
  loadPrefs,
  savePrefs,
  sanitizeMessageContent,
  sanitizeMessages,
  STORAGE_VERSION,
  MAX_LOADED_MESSAGE_CHARS,
  MAX_STORED_MESSAGES,
} from '../aiChatPrefs'
import type { ChatMessage } from '@/domain/model/aiChat'

describe('aiChatPrefs：envelope 读写', () => {
  beforeEach(() => localStorage.clear())

  it('savePrefs → loadPrefs 往返（版本一致）', () => {
    savePrefs('test-key', { a: 1, b: 'x' })
    expect(loadPrefs<{ a: number; b: string }>('test-key')).toEqual({ a: 1, b: 'x' })
  })

  it('版本不一致返回 null', () => {
    localStorage.setItem('test-key', JSON.stringify({ version: 999, data: { a: 1 } }))
    expect(loadPrefs('test-key')).toBeNull()
  })

  it('损坏 JSON 返回 null', () => {
    localStorage.setItem('test-key', '{broken')
    expect(loadPrefs('test-key')).toBeNull()
  })
})

describe('aiChatPrefs：sanitize 截断', () => {
  it('单条内容超 40k 字符截断 + 后缀', () => {
    const content = 'a'.repeat(MAX_LOADED_MESSAGE_CHARS + 100)
    const result = sanitizeMessageContent(content)
    expect(result.length).toBe(MAX_LOADED_MESSAGE_CHARS + '\n\n[...]'.length)
    expect(result.endsWith('\n\n[...]')).toBe(true)
  })

  it('短内容原样返回', () => {
    expect(sanitizeMessageContent('短消息')).toBe('短消息')
  })

  it('消息列表总量超限截断（单条 40k 生效）', () => {
    const messages: ChatMessage[] = [
      {
        key: 'm1',
        from: 'user',
        versions: [{ id: 'm1-v1', content: 'a'.repeat(MAX_LOADED_MESSAGE_CHARS + 50) }],
      },
    ]
    const result = sanitizeMessages(messages)
    expect(result[0].versions[0].content.length).toBe(
      MAX_LOADED_MESSAGE_CHARS + '\n\n[...]'.length
    )
  })

  it('超过 100 条上限截断', () => {
    const messages: ChatMessage[] = Array.from({ length: 120 }, (_, i) => ({
      key: `m${i}`,
      from: 'user' as const,
      versions: [{ id: `m${i}-v1`, content: 'x' }],
    }))
    const result = sanitizeMessages(messages)
    expect(result.length).toBeLessThanOrEqual(MAX_STORED_MESSAGES)
  })
})

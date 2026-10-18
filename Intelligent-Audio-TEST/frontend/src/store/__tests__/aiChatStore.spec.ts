/**
 * 灵犀Agent 会话 Store 测试（§3.7 URL 契约上下文 / §3.11 无供应商/无模型语义化引导；
 * Demo 态对话由用户自配 LLM 供应商驱动，无供应商/无模型时不发起请求）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAiChatStore } from '../aiChatStore'
import { ERROR_MESSAGES, MESSAGE_STATUS } from '@/domain/constants/aiChat'

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
})

describe('aiChatStore：bindContext（§3.7 URL 契约）', () => {
  it('report 进入态：绑定报告上下文 + 报告类型 task', () => {
    const store = useAiChatStore()
    store.bindContext({ report: '42' })
    expect(store.config.reportContextId).toBe('42')
    expect(store.config.reportContextType).toBe('task')
    expect(store.config.reportContextLabel).toContain('42')
  })

  it('task 进入态：绑定任务上下文（task_context）', () => {
    const store = useAiChatStore()
    store.bindContext({ task: '7' })
    expect(store.config.reportContextId).toBe('7')
    expect(store.config.reportContextType).toBe('task_context')
  })
})

describe('aiChatStore：发送守卫（§3.11 无供应商/无模型语义化引导，不发起请求）', () => {
  it('无供应商：追加 user 消息 + assistant 错误消息（noProviderChat）', () => {
    const store = useAiChatStore()
    store.handleSendMessage('生成一份报告')
    expect(store.messages.length).toBe(2)
    expect(store.messages[0].from).toBe('user')
    expect(store.messages[1].status).toBe(MESSAGE_STATUS.ERROR)
    expect(store.messages[1].versions[0].content).toBe(ERROR_MESSAGES.noProviderChat)
    expect(store.isGenerating).toBe(false)
  })

  it('有供应商但无模型：noModel 错误', () => {
    const store = useAiChatStore()
    store.addProvider({
      name: 'OpenAI',
      baseUrl: 'https://api.openai.com/v1',
      apiKey: 'sk-test',
      models: ['gpt-4o'],
    })
    store.handleSendMessage('你好')
    expect(store.messages[1].status).toBe(MESSAGE_STATUS.ERROR)
    expect(store.messages[1].versions[0].content).toBe(ERROR_MESSAGES.noModel)
  })
})

describe('aiChatStore：清空与供应商默认（§3.11 默认=首个添加）', () => {
  it('clearMessages 清空消息 + 移除本地缓存', () => {
    const store = useAiChatStore()
    store.handleSendMessage('x')
    expect(store.messages.length).toBeGreaterThan(0)
    store.clearMessages()
    expect(store.messages.length).toBe(0)
    expect(localStorage.getItem('iatp:ai-chat:v1:messages')).toBeNull()
  })

  it('首个添加的供应商自动为默认', () => {
    const store = useAiChatStore()
    const first = store.addProvider({ name: 'A', baseUrl: 'https://a', apiKey: '', models: [] })
    store.addProvider({ name: 'B', baseUrl: 'https://b', apiKey: '', models: [] })
    expect(store.defaultProvider?.id).toBe(first.id)
    expect(first.isDefault).toBe(true)
  })
})

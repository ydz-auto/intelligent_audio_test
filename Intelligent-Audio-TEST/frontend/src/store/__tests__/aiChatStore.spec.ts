/**
 * 灵犀Agent 会话 Store 测试（§3.7 URL 契约上下文 / §3.11 无供应商/无模型语义化引导；
 * Demo 态对话由用户自配 LLM 供应商驱动，无供应商/无模型时不发起请求）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAiChatStore } from '../aiChatStore'
import { llmProviderApi } from '@/infrastructure/api/llmProviderApi'
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

  it('有供应商带模型：添加后自动选首个模型（配置即用，INT-1109 对齐 React INT-1032）', () => {
    const store = useAiChatStore()
    store.addProvider({
      name: 'OpenAI',
      baseUrl: 'https://api.openai.com/v1',
      apiKey: 'sk-test',
      models: ['gpt-4o', 'gpt-4o-mini'],
    })
    expect(store.config.providerId).toBe(store.providers[0].id)
    expect(store.config.modelId).toBe('gpt-4o')
  })

  it('有供应商但模型清单为空：noModel 错误（无法自动落模型）', () => {
    const store = useAiChatStore()
    store.addProvider({
      name: 'OpenAI',
      baseUrl: 'https://api.openai.com/v1',
      apiKey: 'sk-test',
      models: [],
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

/**
 * 请求体回归（审计 P1：buildChatHistory 结尾总会推入当前 user 指令，
 * 历史数组里再含同一条 user 消息就会重复发送 → 发送/重生成/编辑重发三种入口
 * 都必须保证当前 user 内容只出现一次）。
 */
describe('aiChatStore：发送请求体（当前 user 消息只出现一次，P1 回归）', () => {
  const REPLY = '已为您处理。'
  let sendChatCompletionMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    sendChatCompletionMock = vi
      .spyOn(llmProviderApi, 'sendChatCompletion')
      .mockResolvedValue(REPLY)
  })

  afterEach(() => {
    sendChatCompletionMock.mockRestore()
  })

  function setupWithProvider(): ReturnType<typeof useAiChatStore> {
    const store = useAiChatStore()
    const provider = store.addProvider({
      name: 'Mock',
      baseUrl: 'https://mock.example/v1',
      apiKey: 'sk-test',
      models: ['mock-model'],
    })
    store.updateConfig({ providerId: provider.id, modelId: 'mock-model' })
    return store
  }

  /** 抽取请求体里的 user 消息内容（system 忽略） */
  function requestUserContents(callIndex = 0): string[] {
    const messages: Array<{ role: string; content: string }> =
      sendChatCompletionMock.mock.calls[callIndex][0].messages
    return messages.filter((m) => m.role === 'user').map((m) => m.content)
  }

  it('发送：请求体当前 user 消息只出现一次', () => {
    const store = setupWithProvider()
    store.handleSendMessage('生成一份报告')
    expect(sendChatCompletionMock).toHaveBeenCalledTimes(1)
    expect(requestUserContents()).toEqual(['生成一份报告'])
    store.stopGeneration()
  })

  it('重新生成：原 user 指令只出现一次（请求体不含重复指令）', () => {
    const store = setupWithProvider()
    store.messages = [
      { key: 'u1', from: 'user', versions: [{ id: 'u1-v1', content: '第一问' }], createdAt: 1 },
      {
        key: 'a1',
        from: 'assistant',
        versions: [{ id: 'a1-v1', content: '第一答' }],
        createdAt: 2,
        status: MESSAGE_STATUS.COMPLETE,
      },
    ]
    store.handleRegenerateMessage('a1')
    expect(sendChatCompletionMock).toHaveBeenCalledTimes(1)
    expect(requestUserContents()).toEqual(['第一问'])
    store.stopGeneration()
  })

  it('编辑后重发：当前 user 消息只出现一次', () => {
    const store = setupWithProvider()
    store.messages = [
      { key: 'u1', from: 'user', versions: [{ id: 'u1-v1', content: '第一问' }], createdAt: 1 },
      {
        key: 'a1',
        from: 'assistant',
        versions: [{ id: 'a1-v1', content: '第一答' }],
        createdAt: 2,
        status: MESSAGE_STATUS.COMPLETE,
      },
    ]
    store.handleEditMessage('u1')
    store.applyEdit('第一问（改）', true)
    expect(sendChatCompletionMock).toHaveBeenCalledTimes(1)
    expect(requestUserContents()).toEqual(['第一问（改）'])
    store.stopGeneration()
  })
})

/**
 * 截断重建回归（审计 P2：重生成必须在发送前把旧 assistant 回复从会话截断，
 * 由新回复替换；否则旧答残留并污染后续请求体上下文）。
 */
describe('aiChatStore：重新生成截断重建（P2 回归）', () => {
  const REPLY = '已为您处理。'
  let sendChatCompletionMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    sendChatCompletionMock = vi
      .spyOn(llmProviderApi, 'sendChatCompletion')
      .mockResolvedValue(REPLY)
  })

  afterEach(() => {
    sendChatCompletionMock.mockRestore()
  })

  function setupWithProvider(): ReturnType<typeof useAiChatStore> {
    const store = useAiChatStore()
    const provider = store.addProvider({
      name: 'Mock',
      baseUrl: 'https://mock.example/v1',
      apiKey: 'sk-test',
      models: ['mock-model'],
    })
    store.updateConfig({ providerId: provider.id, modelId: 'mock-model' })
    return store
  }

  it('重生成后旧答被截断：消息列表回到原 user 指令处 + 新回复 loading（旧答不残留）', () => {
    const store = setupWithProvider()
    store.messages = [
      { key: 'u1', from: 'user', versions: [{ id: 'u1-v1', content: '第一问' }], createdAt: 1 },
      {
        key: 'a1',
        from: 'assistant',
        versions: [{ id: 'a1-v1', content: '第一答' }],
        createdAt: 2,
        status: MESSAGE_STATUS.COMPLETE,
      },
    ]
    store.handleRegenerateMessage('a1')
    // 截断重建：旧 assistant 回复移除，列表 = [原 user 指令, 新回复 loading]
    expect(store.messages).toHaveLength(2)
    expect(store.messages[0].key).toBe('u1')
    expect(store.messages[0].from).toBe('user')
    expect(store.messages[1].from).toBe('assistant')
    expect(store.messages[1].status).toBe(MESSAGE_STATUS.LOADING)
    expect(store.messages.map((m) => m.versions[m.versions.length - 1]?.content)).not.toContain(
      '第一答'
    )
    store.stopGeneration()
  })
})

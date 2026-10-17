/**
 * use-chat-handler 单测（INT-598 §3.11/§3.10 2026-10-17 审计 P1 返修）：
 * Demo 对话由用户自配 LLM 供应商驱动——无供应商/无模型 → 语义化错误消息（不杜撰数据）；
 * 已配置供应商 → 真实 POST /chat/completions（mock fetch），正文本地逐块渲染至 complete，
 * 消息体不含杜撰工具卡/来源（toolCalls/sourceRefs 恒空）。
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ERROR_MESSAGES, MESSAGE_STATUS } from '@/features/ai-chat/constants'
import { useChatHandler } from '@/features/ai-chat/hooks/use-chat-handler'
import { useChatConversation } from '@/features/ai-chat/hooks/use-chat-conversation'
import type { ChatConfig, ChatMessage, LlmProvider } from '@/domain/models/aiChat'

const PROVIDER: LlmProvider = {
  id: 'p1',
  name: 'OpenAI',
  baseUrl: 'https://api.openai.com/v1',
  apiKey: 'sk-test',
  models: ['gpt-4o'],
}

const CONFIG: ChatConfig = { providerId: 'p1', modelId: 'gpt-4o' }

function makeJsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 等待 assistant 消息落到 complete/error 终态（真实定时器轮询，流式本地渲染约 200ms） */
async function waitAssistantSettled(
  latestRef: { current: ChatMessage[] }
): Promise<ChatMessage> {
  for (let i = 0; i < 60; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 40))
    const assistant = latestRef.current[1]
    if (
      assistant &&
      (assistant.status === MESSAGE_STATUS.COMPLETE ||
        assistant.status === MESSAGE_STATUS.ERROR)
    ) {
      return assistant
    }
  }
  return latestRef.current[1]
}

/** 等待「最后一条渲染中的 assistant」落到终态（重新生成场景消息位置不定） */
async function waitRegeneratedAssistantSettled(
  latestRef: { current: ChatMessage[] }
): Promise<ChatMessage> {
  for (let i = 0; i < 60; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 40))
    const assistants = latestRef.current.filter(
      (m) => m.from === 'assistant' && m.key.startsWith('assistant-')
    )
    const latest = assistants[assistants.length - 1]
    if (
      latest &&
      (latest.status === MESSAGE_STATUS.COMPLETE ||
        latest.status === MESSAGE_STATUS.ERROR)
    ) {
      return latest
    }
  }
  const assistants = latestRef.current.filter((m) => m.from === 'assistant')
  return assistants[assistants.length - 1]
}

describe('useChatHandler（供应商驱动 Demo 对话，P1 返修）', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('无供应商：追加语义化错误消息，不产生杜撰回复', async () => {
    const latestRef: { current: ChatMessage[] } = { current: [] }
    const { result } = renderHook(() =>
      useChatHandler({
        config: { providerId: 'p-none' },
        provider: null,
        messages: [],
        onMessageUpdate: (updater) => {
          latestRef.current = updater(latestRef.current)
        },
      })
    )

    await act(async () => {
      result.current.sendChat('解读这份报告的核心指标')
    })

    expect(latestRef.current).toHaveLength(2)
    expect(latestRef.current[0].from).toBe('user')
    const assistant = latestRef.current[1]
    expect(assistant.status).toBe(MESSAGE_STATUS.ERROR)
    expect(assistant.versions[0].content).toBe(ERROR_MESSAGES.noProviderChat)
    // 红线：错误消息不含任何杜撰工具卡/来源/推理
    expect(assistant.toolCalls).toBeUndefined()
    expect(assistant.sourceRefs).toBeUndefined()
    expect(assistant.reasoning).toBeUndefined()
  })

  it('已配置供应商+模型：真实 /chat/completions 响应逐块渲染至 complete，无工具卡/来源', async () => {
    const replyText = '这是来自供应商的真实回复，不含杜撰报告数值。'
    const fetchMock = vi.fn().mockResolvedValue(
      makeJsonResponse({
        choices: [{ message: { content: replyText } }],
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    const latestRef: { current: ChatMessage[] } = { current: [] }
    const { result } = renderHook(() =>
      useChatHandler({
        config: CONFIG,
        provider: PROVIDER,
        messages: [],
        onMessageUpdate: (updater) => {
          latestRef.current = updater(latestRef.current)
        },
      })
    )

    await act(async () => {
      result.current.sendChat('你好，帮我看看这份报告')
    })
    const assistant = await waitAssistantSettled(latestRef)

    // 请求体校验：POST 用户 Base URL /chat/completions，OpenAI 兼容 messages
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('https://api.openai.com/v1/chat/completions')
    const body = JSON.parse(String(init?.body))
    expect(body.model).toBe('gpt-4o')
    expect(body.stream).toBe(false)
    expect(body.messages.at(-1)).toEqual({
      role: 'user',
      content: '你好，帮我看看这份报告',
    })

    expect(assistant.status).toBe(MESSAGE_STATUS.COMPLETE)
    expect(assistant.versions[0].content).toBe(replyText)
    // 红线：真实供应商响应不含杜撰工具卡/来源
    expect(assistant.toolCalls).toBeUndefined()
    expect(assistant.sourceRefs).toBeUndefined()
  })

  it('供应商请求失败：落语义化错误消息（HTTP 状态文案）', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(makeJsonResponse({ error: 'bad' }, 401))
    )

    const latestRef: { current: ChatMessage[] } = { current: [] }
    const { result } = renderHook(() =>
      useChatHandler({
        config: CONFIG,
        provider: PROVIDER,
        messages: [],
        onMessageUpdate: (updater) => {
          latestRef.current = updater(latestRef.current)
        },
      })
    )

    await act(async () => {
      result.current.sendChat('你好')
    })
    const assistant = await waitAssistantSettled(latestRef)

    expect(assistant.status).toBe(MESSAGE_STATUS.ERROR)
    expect(assistant.versions[0].content).toContain('认证失败')
    expect(assistant.toolCalls).toBeUndefined()
    expect(assistant.sourceRefs).toBeUndefined()
  })

  it('重新生成（historyMessages override）：请求体用截断后历史，不含旧 assistant 回复与重复 user 指令（P2-4）', async () => {
    const replyText = '重新生成的回复'
    const fetchMock = vi.fn().mockResolvedValue(
      makeJsonResponse({
        choices: [{ message: { content: replyText } }],
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    const makeMsg = (
      key: string,
      from: 'user' | 'assistant',
      content: string,
      status = MESSAGE_STATUS.COMPLETE
    ): ChatMessage => ({
      key,
      from,
      versions: [{ id: `${key}-v1`, content }],
      status,
      createdAt: Date.now(),
    })
    const initialMessages = [
      makeMsg('u1', 'user', '第一问'),
      makeMsg('a1', 'assistant', '第一答'),
      makeMsg('u2', 'user', '第二问'),
      makeMsg('a2', 'assistant', '旧第二答'),
    ]

    const latestRef: { current: ChatMessage[] } = { current: initialMessages }
    const { result } = renderHook(() => {
      const handler = useChatHandler({
        config: CONFIG,
        provider: PROVIDER,
        messages: initialMessages,
        onMessageUpdate: (updater) => {
          latestRef.current = updater(latestRef.current)
        },
      })
      const conversation = useChatConversation({
        messages: initialMessages,
        updateMessages: (updater) => {
          latestRef.current = updater(latestRef.current)
        },
        sendChat: handler.sendChat,
      })
      return { ...handler, ...conversation }
    })

    await act(async () => {
      result.current.handleRegenerateMessage(initialMessages[3])
    })
    const assistant = await waitRegeneratedAssistantSettled(latestRef)

    // 重新生成的 assistant 回复完整渲染
    expect(assistant.versions[0].content).toBe(replyText)

    // 请求体校验：截断后历史 + 当前指令，无旧 assistant 回复、无重复指令
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [, init] = fetchMock.mock.calls[0]
    const body = JSON.parse(String(init?.body))
    const contents = body.messages.map((m: { role: string; content: string }) => m.content)
    expect(contents).not.toContain('旧第二答')
    // 「第二问」仅作为当前指令出现一次
    expect(contents.filter((c: string) => c === '第二问')).toHaveLength(1)
    // 首条为系统提示，末条为当前 user 指令，中间为第一轮完整交换
    expect(body.messages[0].role).toBe('system')
    expect(body.messages.at(-1)).toEqual({ role: 'user', content: '第二问' })
    expect(body.messages.map((m: { role: string }) => m.role)).toEqual([
      'system',
      'user',
      'assistant',
      'user',
    ])
  })
})

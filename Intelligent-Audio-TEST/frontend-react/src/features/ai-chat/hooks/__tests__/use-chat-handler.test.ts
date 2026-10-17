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
})

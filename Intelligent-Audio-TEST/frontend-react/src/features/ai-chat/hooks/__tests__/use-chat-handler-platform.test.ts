/**
 * useChatHandler 平台 Agent 通道单测（INT-2457 §12.2）：
 * message_delta 逐字渲染、tool_call/tool_result 工具卡、run_finished 终态、
 * 取消（只发一次取消请求）、错误归一（Agent 总开关关闭）。
 * Agent API 用替身；端到端（真实 POST /runs + SSE）待 INT-2451/INT-2456 部署后补证。
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useChatHandler } from '@/features/ai-chat/hooks/use-chat-handler'
import { MESSAGE_STATUS } from '@/features/ai-chat/constants'
import { AGENT_ERROR_COPY, AGENT_RUN_STATUS } from '@/domain/models/agent'
import { CHAT_CHANNEL, type ChatMessage } from '@/domain/models/aiChat'
import {
  cancelAgentRun,
  createAgentRun,
  createAgentSession,
  subscribeAgentRunEvents,
  type SubscribeAgentRunEventsOptions,
} from '@/infrastructure/api/agentApi'
import { ApiError } from '@/infrastructure/api/api-error'

vi.mock('@/infrastructure/api/agentApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/infrastructure/api/agentApi')>()
  return {
    ...actual,
    createAgentSession: vi.fn(),
    createAgentRun: vi.fn(),
    cancelAgentRun: vi.fn(),
    getAgentRun: vi.fn(),
    subscribeAgentRunEvents: vi.fn(),
  }
})

const createSessionMock = vi.mocked(createAgentSession)
const createRunMock = vi.mocked(createAgentRun)
const cancelRunMock = vi.mocked(cancelAgentRun)
const subscribeMock = vi.mocked(subscribeAgentRunEvents)

let streamOptions: SubscribeAgentRunEventsOptions | null = null
let latest: ChatMessage[] = []

function renderPlatformChat(extra?: { systemPrompt?: string }) {
  return renderHook(() =>
    useChatHandler({
      channel: CHAT_CHANNEL.PLATFORM,
      config: { chatMode: CHAT_CHANNEL.PLATFORM },
      provider: null,
      messages: latest,
      onMessageUpdate: (updater) => {
        latest = updater(latest)
      },
      systemPrompt: extra?.systemPrompt,
    })
  )
}

beforeEach(() => {
  latest = []
  streamOptions = null
  createSessionMock.mockResolvedValue({ id: 's-1', title: '会话' })
  createRunMock.mockResolvedValue({
    id: 'r-1',
    sessionId: 's-1',
    status: AGENT_RUN_STATUS.RUNNING,
  })
  subscribeMock.mockImplementation((_runId, options) => {
    streamOptions = options
    return () => undefined
  })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('useChatHandler 平台 Agent 通道', () => {
  it('发送 → message_delta 逐字渲染 → run_finished 完成', async () => {
    const { result } = renderPlatformChat()

    await act(async () => {
      result.current.sendChat('帮我对比报告')
    })

    expect(result.current.isGenerating).toBe(true)
    expect(latest).toHaveLength(2)
    expect(latest[0].from).toBe('user')
    expect(latest[1].status).toBe(MESSAGE_STATUS.LOADING)
    expect(createRunMock).toHaveBeenCalledTimes(1)

    act(() => {
      streamOptions?.onEvent({
        type: 'message_delta',
        runId: 'r-1',
        sequence: 1,
        timestamp: 't',
        messageId: 'm-1',
        delta: '正在',
      })
      streamOptions?.onEvent({
        type: 'message_delta',
        runId: 'r-1',
        sequence: 2,
        timestamp: 't',
        messageId: 'm-1',
        delta: '分析',
      })
    })

    expect(latest[1].status).toBe(MESSAGE_STATUS.STREAMING)
    expect(latest[1].versions[0].content).toBe('正在分析')

    act(() => {
      streamOptions?.onEvent({
        type: 'run_finished',
        runId: 'r-1',
        sequence: 3,
        timestamp: 't',
        status: AGENT_RUN_STATUS.SUCCEEDED,
      })
    })

    expect(latest[1].status).toBe(MESSAGE_STATUS.COMPLETE)
    expect(latest[1].versions[0].content).toBe('正在分析')
    expect(result.current.isGenerating).toBe(false)
  })

  it('tool_call / tool_result → 工具卡状态与来源', async () => {
    const { result } = renderPlatformChat()
    await act(async () => {
      result.current.sendChat('查一下报告指标')
    })

    act(() => {
      streamOptions?.onEvent({
        type: 'tool_call',
        runId: 'r-1',
        sequence: 1,
        timestamp: 't',
        toolCallId: 'tc-1',
        tool: 'report_query_metrics',
        risk: 'READ',
        summary: '查询报告 12 指标',
      })
      streamOptions?.onEvent({
        type: 'tool_result',
        runId: 'r-1',
        sequence: 2,
        timestamp: 't',
        toolCallId: 'tc-1',
        status: 'SUCCEEDED',
        summary: '返回 8 项指标',
        sourceRefs: [{ reportId: 12, metricId: 'pass_rate' }],
      })
    })

    const calls = latest[1].toolCalls ?? []
    expect(calls).toHaveLength(1)
    expect(calls[0]).toMatchObject({
      id: 'tc-1',
      tool: 'report_query_metrics',
      label: '查询报告指标',
      status: 'completed',
      summary: '返回 8 项指标',
      sourceRefs: [{ reportId: 12, metricId: 'pass_rate' }],
    })
  })

  it('取消：连续两次 stopGeneration 只发一次取消请求，终态落 CANCELLED 徽标', async () => {
    cancelRunMock.mockResolvedValue({
      id: 'r-1',
      sessionId: 's-1',
      status: AGENT_RUN_STATUS.CANCELLED,
    })
    const { result } = renderPlatformChat()
    await act(async () => {
      result.current.sendChat('长任务')
    })

    act(() => {
      streamOptions?.onEvent({
        type: 'message_delta',
        runId: 'r-1',
        sequence: 1,
        timestamp: 't',
        messageId: 'm-1',
        delta: '部分输出',
      })
    })

    await act(async () => {
      result.current.stopGeneration()
      result.current.stopGeneration()
    })

    expect(cancelRunMock).toHaveBeenCalledTimes(1)
    expect(result.current.isCancelling).toBe(false)
    expect(latest[1].status).toBe(MESSAGE_STATUS.COMPLETE)
    expect(latest[1].runStatus).toBe(AGENT_RUN_STATUS.CANCELLED)
    expect(latest[1].versions[0].content).toBe('部分输出')
  })

  it('Agent 总开关关闭（503 + AGENT_DISABLED）→ error 消息 + 未开启文案，无杜撰内容', async () => {
    createRunMock.mockRejectedValue(
      new ApiError({
        httpStatus: 503,
        detail: { code: 'AGENT_DISABLED', message: 'Agent 未启用' },
      })
    )
    const { result } = renderPlatformChat()

    await act(async () => {
      result.current.sendChat('你好')
    })

    expect(isGeneratingAfterSend(result)).toBe(false)
    expect(latest[1].status).toBe(MESSAGE_STATUS.ERROR)
    expect(latest[1].versions[0].content).toBe(AGENT_ERROR_COPY.disabled)
    expect(latest[1].toolCalls).toBeUndefined()
    expect(latest[1].sourceRefs).toBeUndefined()
  })

  it('agent_service 不可达（503 无总开关码）→ 报服务暂不可用，不误报未开启', async () => {
    createRunMock.mockRejectedValue(
      new ApiError({ httpStatus: 503, detail: 'agent service unavailable' })
    )
    const { result } = renderPlatformChat()

    await act(async () => {
      result.current.sendChat('你好')
    })

    expect(latest[1].status).toBe(MESSAGE_STATUS.ERROR)
    expect(latest[1].versions[0].content).toBe(AGENT_ERROR_COPY.serviceUnavailable)
  })

  it('run 失败但已有正文：保留正文 + FAILED 徽标，不清空内容', async () => {
    const { result } = renderPlatformChat()
    await act(async () => {
      result.current.sendChat('你好')
    })

    act(() => {
      streamOptions?.onEvent({
        type: 'message_delta',
        runId: 'r-1',
        sequence: 1,
        timestamp: 't',
        messageId: 'm-1',
        delta: '已有正文',
      })
      streamOptions?.onEvent({
        type: 'run_finished',
        runId: 'r-1',
        sequence: 2,
        timestamp: 't',
        status: AGENT_RUN_STATUS.FAILED,
        error: '工具连续失败',
      })
    })

    expect(latest[1].status).toBe(MESSAGE_STATUS.COMPLETE)
    expect(latest[1].runStatus).toBe(AGENT_RUN_STATUS.FAILED)
    expect(latest[1].versions[0].content).toBe('已有正文')
  })
})

function isGeneratingAfterSend(result: { current: { isGenerating: boolean } }): boolean {
  return result.current.isGenerating
}

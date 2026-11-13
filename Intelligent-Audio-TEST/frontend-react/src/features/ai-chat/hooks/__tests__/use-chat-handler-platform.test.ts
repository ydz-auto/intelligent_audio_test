/**
 * useChatHandler 平台 Agent 通道单测（INT-2457 §12.2 + INT-2507）：
 * message_delta 逐字渲染、tool_call/tool_result 工具卡、run_finished 终态、
 * 取消（只发一次取消请求）、错误归一（Agent 总开关关闭），以及两个宿主（整页 / 浮窗）
 * 共享同一 run 状态、不会并发各跑一条 run。
 * Agent API 用替身；端到端（真实 POST /runs + SSE）见交付评论中的真实栈证据。
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useChatHandler } from '@/features/ai-chat/hooks/use-chat-handler'
import { MESSAGE_STATUS } from '@/features/ai-chat/constants'
import { AGENT_ERROR_COPY, AGENT_RUN_STATUS } from '@/domain/models/agent'
import { CHAT_CHANNEL } from '@/domain/models/aiChat'
import { useAgentRunStore } from '@/application/agent/agent-run-store'
import { useAiChatSession } from '@/infrastructure/stores/aiChatSessionStore'
import {
  cancelAgentRun,
  createAgentRun,
  createAgentSession,
  getAgentSession,
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
    getAgentSession: vi.fn(),
    subscribeAgentRunEvents: vi.fn(),
  }
})

const createSessionMock = vi.mocked(createAgentSession)
const createRunMock = vi.mocked(createAgentRun)
const cancelRunMock = vi.mocked(cancelAgentRun)
const getSessionMock = vi.mocked(getAgentSession)
const subscribeMock = vi.mocked(subscribeAgentRunEvents)

let streamOptions: SubscribeAgentRunEventsOptions | null = null

/** 共享消息列表（平台通道由 agent-run-store 直接写入 store，不再经调用方 onMessageUpdate） */
const messages = () => useAiChatSession.getState().messages

function renderPlatformChat(extra?: { systemPrompt?: string }) {
  return renderHook(() =>
    useChatHandler({
      channel: CHAT_CHANNEL.PLATFORM,
      config: { chatMode: CHAT_CHANNEL.PLATFORM },
      provider: null,
      messages: messages(),
      onMessageUpdate: useAiChatSession.getState().updateMessages,
      systemPrompt: extra?.systemPrompt,
    })
  )
}

beforeEach(() => {
  window.localStorage.clear()
  useAgentRunStore.getState().reset()
  useAiChatSession.setState({
    messages: [],
    agentSessionId: null,
    agentRunId: null,
  })
  window.localStorage.clear()
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
  getSessionMock.mockResolvedValue({
    session: { id: 's-1', title: '会话' },
    messages: [],
    runs: [],
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
    expect(messages()).toHaveLength(2)
    expect(messages()[0].from).toBe('user')
    expect(messages()[1].status).toBe(MESSAGE_STATUS.LOADING)
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

    expect(messages()[1].status).toBe(MESSAGE_STATUS.STREAMING)
    expect(messages()[1].versions[0].content).toBe('正在分析')

    act(() => {
      streamOptions?.onEvent({
        type: 'run_finished',
        runId: 'r-1',
        sequence: 3,
        timestamp: 't',
        status: AGENT_RUN_STATUS.SUCCEEDED,
      })
    })

    expect(messages()[1].status).toBe(MESSAGE_STATUS.COMPLETE)
    expect(messages()[1].versions[0].content).toBe('正在分析')
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

    const calls = messages()[1].toolCalls ?? []
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
    expect(messages()[1].status).toBe(MESSAGE_STATUS.COMPLETE)
    expect(messages()[1].runStatus).toBe(AGENT_RUN_STATUS.CANCELLED)
    expect(messages()[1].versions[0].content).toBe('部分输出')
  })

  it('Agent 总开关关闭（503）→ error 消息 + 中文文案，无杜撰内容', async () => {
    createRunMock.mockRejectedValue(new ApiError({ httpStatus: 503 }))
    const { result } = renderPlatformChat()

    await act(async () => {
      result.current.sendChat('你好')
    })

    expect(result.current.isGenerating).toBe(false)
    expect(messages()[1].status).toBe(MESSAGE_STATUS.ERROR)
    expect(messages()[1].versions[0].content).toBe(AGENT_ERROR_COPY.disabled)
    expect(messages()[1].toolCalls).toBeUndefined()
    expect(messages()[1].sourceRefs).toBeUndefined()
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

    expect(messages()[1].status).toBe(MESSAGE_STATUS.COMPLETE)
    expect(messages()[1].runStatus).toBe(AGENT_RUN_STATUS.FAILED)
    expect(messages()[1].versions[0].content).toBe('已有正文')
  })

  it('两宿主同源（INT-2507）：整页与浮窗同时打开时只有一条 run、两侧生成态同步', async () => {
    const pageHost = renderPlatformChat()
    const floatingHost = renderPlatformChat()

    await act(async () => {
      pageHost.result.current.sendChat('整页的问题')
    })
    expect(pageHost.result.current.isGenerating).toBe(true)
    expect(floatingHost.result.current.isGenerating).toBe(true)

    // 浮窗再发：共享单 run 闸拦下
    await act(async () => {
      floatingHost.result.current.sendChat('浮窗并发的问题')
    })
    expect(createRunMock).toHaveBeenCalledTimes(1)
    expect(messages()).toHaveLength(2)

    // 事件只写一份 assistant 气泡
    act(() => {
      streamOptions?.onEvent({
        type: 'message_delta',
        runId: 'r-1',
        sequence: 1,
        timestamp: 't',
        messageId: 'm-1',
        delta: '唯一',
      })
    })
    expect(messages()).toHaveLength(2)
    expect(messages()[1].versions[0].content).toBe('唯一')

    act(() => {
      streamOptions?.onEvent({
        type: 'run_finished',
        runId: 'r-1',
        sequence: 2,
        timestamp: 't',
        status: AGENT_RUN_STATUS.SUCCEEDED,
      })
    })
    expect(pageHost.result.current.isGenerating).toBe(false)
    expect(floatingHost.result.current.isGenerating).toBe(false)
  })
})

/**
 * use-agent-run 单测（INT-2457 §12.2）：发起 run、SSE 事件去重、重连态、取消防重复、错误归一。
 * API 层用 vi.mock 替身（不发真实请求；端到端证据待后端部署后补）。
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AgentRun, AgentRunEvent } from '@/domain/models/agent'
import { AGENT_EVENT_TYPE, AGENT_RUN_STATUS } from '@/domain/models/agent'
import { useAgentRun, AGENT_RUN_PHASE } from '@/application/agent/use-agent-run'
import {
  cancelAgentRun,
  createAgentRun,
  createAgentSession,
  subscribeAgentRunEvents,
} from '@/infrastructure/api/agentApi'
import { ApiError } from '@/infrastructure/api/api-error'
import type { SubscribeAgentRunEventsOptions } from '@/infrastructure/api/agentApi'

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

function messageDelta(sequence: number, messageId: string, delta: string): AgentRunEvent {
  return {
    type: AGENT_EVENT_TYPE.MESSAGE_DELTA,
    runId: 'r-1',
    sequence,
    timestamp: 't',
    messageId,
    delta,
  }
}

function runFinished(sequence: number): AgentRunEvent {
  return {
    type: AGENT_EVENT_TYPE.RUN_FINISHED,
    runId: 'r-1',
    sequence,
    timestamp: 't',
    status: AGENT_RUN_STATUS.SUCCEEDED,
  }
}

/** 捕获 API 层订阅 → 由用例手动推事件 */
let streamOptions: SubscribeAgentRunEventsOptions | null = null

beforeEach(() => {
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

describe('useAgentRun', () => {
  it('发送：建会话一次 → 发起 run → 转发事件', async () => {
    const received: AgentRunEvent[] = []
    const { result } = renderHook(() => useAgentRun({ onEvent: (e) => received.push(e) }))

    await act(async () => {
      await result.current.send('帮我对比报告')
    })

    expect(createSessionMock).toHaveBeenCalledTimes(1)
    expect(createSessionMock.mock.calls[0][0]).toMatchObject({ title: '帮我对比报告' })
    expect(createRunMock).toHaveBeenCalledTimes(1)
    expect(createRunMock.mock.calls[0][0]).toBe('s-1')
    expect(createRunMock.mock.calls[0][1]).toEqual({ message: '帮我对比报告' })
    expect(typeof createRunMock.mock.calls[0][2]).toBe('string')
    expect(subscribeMock).toHaveBeenCalledWith('r-1', expect.anything())
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.RUNNING)

    act(() => {
      streamOptions?.onEvent(messageDelta(1, 'm-1', '你好'))
      streamOptions?.onEvent(runFinished(2))
    })

    expect(received.map((event) => event.type)).toEqual([
      AGENT_EVENT_TYPE.MESSAGE_DELTA,
      AGENT_EVENT_TYPE.RUN_FINISHED,
    ])
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.FINISHED)
    expect(result.current.run?.status).toBe(AGENT_RUN_STATUS.SUCCEEDED)
  })

  it('去重：重连回放的 sequence / message_id 重复事件不再转发', async () => {
    const received: AgentRunEvent[] = []
    const { result } = renderHook(() => useAgentRun({ onEvent: (e) => received.push(e) }))

    await act(async () => {
      await result.current.send('你好')
    })

    act(() => {
      streamOptions?.onEvent(messageDelta(1, 'm-1', 'A'))
      streamOptions?.onEvent(messageDelta(1, 'm-1', 'A')) // 重连回放同一条
      streamOptions?.onEvent(messageDelta(2, 'm-1', 'B'))
      streamOptions?.onEvent(messageDelta(2, 'm-1', 'B')) // 同一 sequence 重复
    })

    expect(received).toHaveLength(2)
    expect(received.map((event) => (event as { delta: string }).delta)).toEqual(['A', 'B'])
  })

  it('重连状态：reconnecting → 提示；open → 回到运行态', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('你好')
    })

    act(() => {
      streamOptions?.onStatus?.('reconnecting')
    })
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.RECONNECTING)
    expect(result.current.streamStatus).toBe('reconnecting')

    act(() => {
      streamOptions?.onStatus?.('open')
    })
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.RUNNING)
  })

  it('取消：连续点击只发一次取消请求，终态落 CANCELLED', async () => {
    let resolveCancel: ((run: AgentRun) => void) | null = null
    cancelRunMock.mockImplementation(
      () =>
        new Promise<AgentRun>((resolve) => {
          resolveCancel = resolve
        })
    )

    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('你好')
    })

    let first!: Promise<string | null>
    let second!: Promise<string | null>
    act(() => {
      first = result.current.cancel()
      second = result.current.cancel()
    })
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.CANCELLING)

    await act(async () => {
      resolveCancel?.({
        id: 'r-1',
        sessionId: 's-1',
        status: AGENT_RUN_STATUS.CANCELLED,
      })
      await Promise.all([first, second])
    })

    expect(cancelRunMock).toHaveBeenCalledTimes(1)
    expect(result.current.run?.status).toBe(AGENT_RUN_STATUS.CANCELLED)
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.FINISHED)
  })

  it('错误归一：Agent 总开关关闭（503）→ error 态 + 中文文案', async () => {
    createRunMock.mockRejectedValue(new ApiError({ httpStatus: 503 }))
    const errors: string[] = []
    const { result } = renderHook(() => useAgentRun({ onError: (m) => errors.push(m) }))

    await act(async () => {
      await result.current.send('你好')
    })

    expect(result.current.phase).toBe(AGENT_RUN_PHASE.ERROR)
    expect(errors[0]).toContain('Agent')
    expect(result.current.error).toBe(errors[0])
  })

  it('reset：清空 run（keepSession 保留会话，默认新建会话）', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('第一轮')
    })

    act(() => {
      result.current.reset({ keepSession: true })
    })
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.IDLE)
    expect(result.current.run).toBeNull()

    await act(async () => {
      await result.current.send('第二轮')
    })
    expect(createSessionMock).toHaveBeenCalledTimes(1) // 复用会话

    act(() => {
      result.current.reset()
    })
    await act(async () => {
      await result.current.send('第三轮')
    })
    expect(createSessionMock).toHaveBeenCalledTimes(2) // 默认新建会话
  })
})

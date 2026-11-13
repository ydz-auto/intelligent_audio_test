/**
 * use-agent-run 单测（INT-2457 §12.2 + INT-2507 单实例回归 + INT-2521 宿主离场取消）：
 * 平台 Agent 的会话 id / run 生命周期收敛在 application/agent/agent-run-store 的模块级
 * 单一实例里。这里覆盖：
 * - 发起 run、SSE 事件去重、重连态、取消防重复、错误归一、reset 语义；
 * - 两宿主（整页 / 浮窗）订阅同一份状态：一侧发 run，另一侧同 phase、无法并发发送；
 * - 展开整页（宿主卸载 → 重新挂载）后仍续用同一服务端会话；
 * - 刷新恢复：getAgentSession 校验会话 / 回填历史 / 会话失效清 id；
 * - INT-2521（按 A5–A7 收窄）：只有最后一个宿主按取消语义离场才中止在办 run。
 * API 层用 vi.mock 替身（不发真实请求；端到端真实栈证据见交付评论）。
 */
import { StrictMode } from 'react'

import { act, renderHook, waitFor } from '@testing-library/react'
import { toast } from 'sonner'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AgentRun, AgentRunEvent } from '@/domain/models/agent'
import {
  AGENT_APPROVAL_COPY,
  AGENT_APPROVAL_STATUS,
  AGENT_ERROR_COPY,
  AGENT_EVENT_TYPE,
  AGENT_RUN_STATUS,
  AGENT_TOOL_RISK,
} from '@/domain/models/agent'
import {
  useAgentRun,
  useAgentRunHost,
  AGENT_RUN_PHASE,
  AGENT_RUN_UNMOUNT_CANCEL_COPY,
} from '@/application/agent/use-agent-run'
import { useAgentRunStore } from '@/application/agent/agent-run-store'
import {
  cancelAgentRun,
  createAgentRun,
  createAgentSession,
  decideAgentApproval,
  getAgentRun,
  getAgentSession,
  listAgentApprovals,
  subscribeAgentRunEvents,
} from '@/infrastructure/api/agentApi'
import { ApiError } from '@/infrastructure/api/api-error'
import type { SubscribeAgentRunEventsOptions } from '@/infrastructure/api/agentApi'
import { useAiChatSession } from '@/infrastructure/stores/aiChatSessionStore'

vi.mock('sonner', () => ({ toast: { info: vi.fn(), error: vi.fn(), success: vi.fn() } }))

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
    listAgentApprovals: vi.fn(),
    decideAgentApproval: vi.fn(),
  }
})

const createSessionMock = vi.mocked(createAgentSession)
const createRunMock = vi.mocked(createAgentRun)
const cancelRunMock = vi.mocked(cancelAgentRun)
const getSessionMock = vi.mocked(getAgentSession)
const subscribeMock = vi.mocked(subscribeAgentRunEvents)
const getRunMock = vi.mocked(getAgentRun)
const listApprovalsMock = vi.mocked(listAgentApprovals)
const decideApprovalMock = vi.mocked(decideAgentApproval)
const toastInfoMock = vi.mocked(toast.info)

/** 离场宽限窗口（store 判定「最后一个宿主离场」用 setTimeout(0)）走完 */
function flushDetachGrace() {
  return new Promise<void>((resolve) => {
    setTimeout(resolve, 0)
  })
}

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

/** 写操作工具调用事件（risk=WRITE，随后由 approval_required 关联审批单） */
function writeToolCall(sequence: number, toolCallId = 'tc-1'): AgentRunEvent {
  return {
    type: AGENT_EVENT_TYPE.TOOL_CALL,
    runId: 'r-1',
    sequence,
    timestamp: 't',
    toolCallId,
    tool: 'memory_write',
    risk: AGENT_TOOL_RISK.WRITE,
    summary: '{"section":"USER_PROFILE"}',
  }
}

/** 审批提案事件（§9.4；载荷形态同后端 approval_required） */
function approvalRequired(
  sequence: number,
  approvalId = 'ap-1',
  toolCallId = 'tc-1'
): AgentRunEvent {
  return {
    type: AGENT_EVENT_TYPE.APPROVAL_REQUIRED,
    runId: 'r-1',
    sequence,
    timestamp: 't',
    approvalId,
    toolCallId,
    tool: 'memory_write',
    risk: AGENT_TOOL_RISK.WRITE,
    expiresAt: '2030-01-01T00:00:00Z',
    proposal: {
      tool: 'memory_write',
      risk: AGENT_TOOL_RISK.WRITE,
      stepId: 'step-1',
      turn: 1,
      arguments: { section: 'USER_PROFILE' },
    },
  }
}

/** 捕获 API 层订阅 → 由用例手动推事件 */
let streamOptions: SubscribeAgentRunEventsOptions | null = null

/** 共享状态复位（模块级 store 跨用例存活，必须每个用例清干净） */
function resetSharedState() {
  window.localStorage.clear()
  // reset() 同时清掉上一个用例遗留的离场宽限定时器与在途补取消标记
  useAgentRunStore.getState().reset()
  // 宿主登记表跨用例清理（'keep' 语义：不触发取消）
  useAgentRunStore.getState().detachHost('page', 'keep')
  useAgentRunStore.getState().detachHost('workbench', 'keep')
  useAiChatSession.setState({
    messages: [],
    agentSessionId: null,
    agentRunId: null,
  })
  window.localStorage.clear()
}

beforeEach(() => {
  streamOptions = null
  resetSharedState()
  createSessionMock.mockResolvedValue({ id: 's-1', title: '会话' })
  createRunMock.mockResolvedValue({
    id: 'r-1',
    sessionId: 's-1',
    status: AGENT_RUN_STATUS.RUNNING,
  })
  // 取消默认落终态（避免用例结束后还挂 2s 的核对定时器污染下一个用例）
  cancelRunMock.mockResolvedValue({
    id: 'r-1',
    sessionId: 's-1',
    status: AGENT_RUN_STATUS.CANCELLED,
  })
  subscribeMock.mockImplementation((_runId, options) => {
    streamOptions = options
    return () => undefined
  })
  // 宿主挂载恢复的默认替身：会话存在且无历史（避免 remount 用例误走 404 清会话）
  getSessionMock.mockResolvedValue({
    session: { id: 's-1', title: '会话' },
    messages: [],
    runs: [],
  })
  listApprovalsMock.mockResolvedValue([])
  getRunMock.mockResolvedValue({
    id: 'r-1',
    sessionId: 's-1',
    status: AGENT_RUN_STATUS.RUNNING,
  })
  decideApprovalMock.mockResolvedValue({
    approval: {
      id: 'ap-1',
      runId: 'r-1',
      status: AGENT_APPROVAL_STATUS.APPROVED,
      proposal: { tool: 'memory_write', risk: AGENT_TOOL_RISK.WRITE },
    },
    runStatus: AGENT_RUN_STATUS.RUNNING,
  })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('useAgentRun（共享单一实例）', () => {
  it('发送：建会话一次 → 发起 run → 事件驱动共享消息列表', async () => {
    const { result } = renderHook(() => useAgentRun())

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
    // 会话 id 落共享 store（两宿主与刷新共用）
    expect(useAiChatSession.getState().agentSessionId).toBe('s-1')
    expect(useAiChatSession.getState().agentRunId).toBe('r-1')
    expect(useAiChatSession.getState().messages).toHaveLength(2)

    act(() => {
      streamOptions?.onEvent(messageDelta(1, 'm-1', '你好'))
      streamOptions?.onEvent(runFinished(2))
    })

    const messages = useAiChatSession.getState().messages
    expect(messages[1].versions[0].content).toBe('你好')
    expect(messages[1].status).toBe('complete')
    expect(messages[1].runStatus).toBe(AGENT_RUN_STATUS.SUCCEEDED)
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.FINISHED)
    expect(result.current.run?.status).toBe(AGENT_RUN_STATUS.SUCCEEDED)
    // 终态后清 run id（不再有进行中的 run）
    expect(useAiChatSession.getState().agentRunId).toBeNull()
  })

  it('两宿主同源（INT-2507 核心）：一侧发 run，另一侧同 phase 且不能再发一条', async () => {
    const hostA = renderHook(() => useAgentRun())
    const hostB = renderHook(() => useAgentRun())

    await act(async () => {
      await hostA.result.current.send('整页发出的问题')
    })

    // 浮窗（另一宿主）看到同一 run 在跑
    expect(hostB.result.current.phase).toBe(AGENT_RUN_PHASE.RUNNING)

    // 另一侧再发：共享单实例的 active 闸拦下，不会起第二条 run
    await act(async () => {
      await hostB.result.current.send('浮窗并发的问题')
    })
    expect(createRunMock).toHaveBeenCalledTimes(1)
    expect(useAiChatSession.getState().messages).toHaveLength(2)

    // 事件只补一份 assistant 气泡（两套补丁器重复拼接的问题不再出现）
    act(() => {
      streamOptions?.onEvent(messageDelta(1, 'm-1', '一份'))
      streamOptions?.onEvent(messageDelta(2, 'm-1', '正文'))
    })
    expect(useAiChatSession.getState().messages).toHaveLength(2)
    expect(useAiChatSession.getState().messages[1].versions[0].content).toBe('一份正文')

    act(() => {
      streamOptions?.onEvent(runFinished(3))
    })
    expect(hostA.result.current.phase).toBe(AGENT_RUN_PHASE.FINISHED)
    expect(hostB.result.current.phase).toBe(AGENT_RUN_PHASE.FINISHED)
  })

  it('展开整页：宿主卸载 → 重新挂载后仍续用同一服务端会话', async () => {
    const floating = renderHook(() => useAgentRun())
    await act(async () => {
      await floating.result.current.send('浮窗里的问题')
    })
    act(() => {
      streamOptions?.onEvent(messageDelta(1, 'm-1', '第一轮回答'))
      streamOptions?.onEvent(runFinished(2))
    })

    // 「展开整页」= 浮窗卸载、/ai-chat 挂载
    floating.unmount()
    const page = renderHook(() => useAgentRun())
    await act(async () => {
      await page.result.current.send('刚才那份报告呢')
    })

    // 没有新建会话，第二条 run 挂在同一个 session 上 → 服务端上下文延续
    expect(createSessionMock).toHaveBeenCalledTimes(1)
    expect(createRunMock).toHaveBeenCalledTimes(2)
    expect(createRunMock.mock.calls[1][0]).toBe('s-1')
    expect(useAiChatSession.getState().agentSessionId).toBe('s-1')
  })

  it('取消：两宿主连续点击只发一次取消请求，终态落 CANCELLED', async () => {
    let resolveCancel: ((run: AgentRun) => void) | null = null
    cancelRunMock.mockImplementation(
      () =>
        new Promise<AgentRun>((resolve) => {
          resolveCancel = resolve
        })
    )

    const hostA = renderHook(() => useAgentRun())
    const hostB = renderHook(() => useAgentRun())
    await act(async () => {
      await hostA.result.current.send('你好')
    })

    let first!: Promise<string | null>
    let second!: Promise<string | null>
    act(() => {
      first = hostA.result.current.cancel()
      second = hostB.result.current.cancel()
    })
    expect(hostA.result.current.phase).toBe(AGENT_RUN_PHASE.CANCELLING)
    expect(hostB.result.current.phase).toBe(AGENT_RUN_PHASE.CANCELLING)

    await act(async () => {
      resolveCancel?.({
        id: 'r-1',
        sessionId: 's-1',
        status: AGENT_RUN_STATUS.CANCELLED,
      })
      await Promise.all([first, second])
    })

    expect(cancelRunMock).toHaveBeenCalledTimes(1)
    expect(hostA.result.current.run?.status).toBe(AGENT_RUN_STATUS.CANCELLED)
    expect(hostA.result.current.phase).toBe(AGENT_RUN_PHASE.FINISHED)
    expect(hostB.result.current.phase).toBe(AGENT_RUN_PHASE.FINISHED)
  })

  it('去重：重连回放的 sequence / message_id 重复事件不再重复拼接正文', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('你好')
    })

    act(() => {
      streamOptions?.onEvent(messageDelta(1, 'm-1', 'A'))
      streamOptions?.onEvent(messageDelta(1, 'm-1', 'A')) // 重连回放同一条
      streamOptions?.onEvent(messageDelta(2, 'm-1', 'B'))
      streamOptions?.onEvent(messageDelta(2, 'm-1', 'B')) // 同一 sequence 重复
    })

    expect(useAiChatSession.getState().messages[1].versions[0].content).toBe('AB')
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

  it('错误归一：Agent 总开关关闭（503 + AGENT_DISABLED）→ error 态 + 中文文案落在 assistant 气泡', async () => {
    createRunMock.mockRejectedValue(
      new ApiError({ httpStatus: 503, detail: { code: 'AGENT_DISABLED', message: 'z' } })
    )
    const { result } = renderHook(() => useAgentRun())

    await act(async () => {
      await result.current.send('你好')
    })

    expect(result.current.phase).toBe(AGENT_RUN_PHASE.ERROR)
    expect(result.current.error).toBe(AGENT_ERROR_COPY.disabled)
    const messages = useAiChatSession.getState().messages
    expect(messages[1].status).toBe('error')
    expect(messages[1].versions[0].content).toBe(result.current.error)
  })

  it('INT-2520 上游中断：等于水位的可恢复 error 帧不去重、不落终态，只提示重连', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('你好')
    })

    act(() => {
      streamOptions?.onEvent(messageDelta(5, 'm-1', 'A'))
      // 网关合成帧：sequence 恒等于已下发水位
      streamOptions?.onEvent({
        type: AGENT_EVENT_TYPE.ERROR,
        runId: 'r-1',
        sequence: 5,
        timestamp: 't',
        errorCode: 'UPSTREAM_UNAVAILABLE',
        errorMessage: '上游事件流转发中断，请按 Last-Event-ID 续传',
        recoverable: true,
      })
    })

    // 不落终态、不报错，页面只停在「重连中」；已下发正文不受影响
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.RECONNECTING)
    expect(result.current.error).toBeNull()
    expect(useAiChatSession.getState().messages[1].versions[0].content).toBe('A')

    // 续传后仍按 sequence 继续应用增量，终态正常收口
    act(() => {
      streamOptions?.onStatus?.('open')
      streamOptions?.onEvent(messageDelta(6, 'm-1', 'B'))
      streamOptions?.onEvent(runFinished(7))
    })
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.FINISHED)
    expect(useAiChatSession.getState().messages[1].versions[0].content).toBe('AB')
  })

  it('INT-2520 终态错误：不可恢复的 error 帧仍判失败并关流', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('你好')
    })

    act(() => {
      streamOptions?.onEvent({
        type: AGENT_EVENT_TYPE.ERROR,
        runId: 'r-1',
        sequence: 1,
        timestamp: 't',
        errorCode: 'RESTART_WRITE_UNVERIFIED',
        errorMessage: '进程重启前的中断写操作需人工确认',
        recoverable: false,
      })
    })

    expect(result.current.phase).toBe(AGENT_RUN_PHASE.ERROR)
    expect(result.current.error).toBe('进程重启前的中断写操作需人工确认')
  })

  it('INT-2520 错误归一：503 服务不可达 → 服务暂不可用文案（不误报未开启）', async () => {
    createRunMock.mockRejectedValue(
      new ApiError({ httpStatus: 503, detail: 'agent service unavailable' })
    )
    const { result } = renderHook(() => useAgentRun())

    await act(async () => {
      await result.current.send('你好')
    })

    expect(result.current.phase).toBe(AGENT_RUN_PHASE.ERROR)
    expect(result.current.error).toBe(AGENT_ERROR_COPY.serviceUnavailable)
  })

  it('INT-2520 错误归一：503 + code=AGENT_DISABLED 仍是「未开启」文案', async () => {
    createRunMock.mockRejectedValue(
      new ApiError({ httpStatus: 503, detail: { code: 'AGENT_DISABLED', message: 'z' } })
    )
    const { result } = renderHook(() => useAgentRun())

    await act(async () => {
      await result.current.send('你好')
    })

    expect(result.current.phase).toBe(AGENT_RUN_PHASE.ERROR)
    expect(result.current.error).toBe(AGENT_ERROR_COPY.disabled)
  })

  it('reset：清空 run（keepSession 保留会话，默认结束会话）', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('第一轮')
    })

    act(() => {
      result.current.reset({ keepSession: true })
    })
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.IDLE)
    expect(result.current.run).toBeNull()
    expect(useAiChatSession.getState().agentSessionId).toBe('s-1')

    await act(async () => {
      await result.current.send('第二轮')
    })
    expect(createSessionMock).toHaveBeenCalledTimes(1) // 复用会话

    act(() => {
      result.current.reset()
    })
    expect(useAiChatSession.getState().agentSessionId).toBeNull()
    await act(async () => {
      await result.current.send('第三轮')
    })
    expect(createSessionMock).toHaveBeenCalledTimes(2) // 默认新建会话
  })
})

describe('useAgentRun 审批卡 + 断线续传（INT-2472）', () => {
  async function startRunWithApproval() {
    const hook = renderHook(() => useAgentRun())
    await act(async () => {
      await hook.result.current.send('记住我的偏好')
    })
    act(() => {
      streamOptions?.onEvent(writeToolCall(1))
      streamOptions?.onEvent(approvalRequired(2))
    })
    return hook
  }

  it('approval_required：审批单入列、工具卡同步、阶段转等待审批、时间线有记录', async () => {
    const { result } = await startRunWithApproval()

    expect(result.current.approvals).toHaveLength(1)
    expect(result.current.approvals[0]).toMatchObject({
      id: 'ap-1',
      runId: 'r-1',
      toolCallId: 'tc-1',
      status: AGENT_APPROVAL_STATUS.PENDING,
    })
    expect(result.current.approvals[0].proposal).toMatchObject({
      tool: 'memory_write',
      risk: AGENT_TOOL_RISK.WRITE,
      stepId: 'step-1',
    })
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.WAITING_APPROVAL)

    // 工具卡与审批卡同源：同一条 tool call 标等待审批，计数不会重复
    const message = useAiChatSession.getState().messages[1]
    expect(message.toolCalls?.[0]).toMatchObject({
      id: 'tc-1',
      risk: AGENT_TOOL_RISK.WRITE,
      approvalId: 'ap-1',
      approvalStatus: AGENT_APPROVAL_STATUS.PENDING,
      status: 'pending',
    })

    // 时间线按后端 sequence 记录工具调用与审批
    const kinds = result.current.timeline.map((entry) => entry.kind)
    expect(kinds).toContain('tool_call')
    expect(kinds).toContain('approval')

    // 流仍开着（等待审批期间不关流），残留的取消定时器等不污染下一个用例
    act(() => {
      streamOptions?.onEvent(runFinished(3))
    })
  })

  it('决策连点：同一条审批单只发一次请求，批准后状态 / 工具卡 / 阶段同步', async () => {
    let resolveDecision: ((value: Awaited<
      ReturnType<typeof decideAgentApproval>
    >) => void) | null = null
    decideApprovalMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveDecision = resolve
        })
    )
    const { result } = await startRunWithApproval()

    let first!: Promise<string | null>
    let second!: Promise<string | null>
    act(() => {
      first = result.current.decideApproval('ap-1', 'APPROVE')
      second = result.current.decideApproval('ap-1', 'APPROVE')
    })
    expect(decideApprovalMock).toHaveBeenCalledTimes(1)
    expect(result.current.decidingApprovalIds).toEqual(['ap-1'])

    await act(async () => {
      resolveDecision?.({
        approval: {
          id: 'ap-1',
          runId: 'r-1',
          toolCallId: 'tc-1',
          status: AGENT_APPROVAL_STATUS.APPROVED,
          proposal: { tool: 'memory_write', risk: AGENT_TOOL_RISK.WRITE },
          decidedBy: 1,
          decidedAt: 't',
        },
        runStatus: AGENT_RUN_STATUS.RUNNING,
      })
      await Promise.all([first, second])
    })

    expect(result.current.approvals[0].status).toBe(
      AGENT_APPROVAL_STATUS.APPROVED
    )
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.RUNNING)
    expect(result.current.decidingApprovalIds).toEqual([])
    const call = useAiChatSession.getState().messages[1].toolCalls?.[0]
    expect(call?.approvalStatus).toBe(AGENT_APPROVAL_STATUS.APPROVED)
    expect(call?.status).toBe('running')

    act(() => {
      streamOptions?.onEvent(runFinished(3))
    })
  })

  it('决策 409（过期 / 并发）：以服务端列表为准刷新卡片并返回统一文案', async () => {
    const { result } = await startRunWithApproval()
    // approval_required 会先对齐一次列表；等它落定后再让后续列表返回已过期
    await waitFor(() => {
      expect(result.current.approvals[0]?.status).toBe(
        AGENT_APPROVAL_STATUS.PENDING
      )
    })
    decideApprovalMock.mockRejectedValue(
      new ApiError({ httpStatus: 409, detail: '审批单已过期，写操作未执行' })
    )
    listApprovalsMock.mockResolvedValue([
      {
        id: 'ap-1',
        runId: 'r-1',
        toolCallId: 'tc-1',
        status: AGENT_APPROVAL_STATUS.EXPIRED,
        proposal: { tool: 'memory_write', risk: AGENT_TOOL_RISK.WRITE },
      },
    ])

    let failure: string | null = null
    await act(async () => {
      failure = await result.current.decideApproval('ap-1', 'APPROVE')
    })

    expect(failure).toBe(AGENT_APPROVAL_COPY.conflict)
    expect(listApprovalsMock).toHaveBeenCalledWith('r-1')
    expect(result.current.approvals[0].status).toBe(
      AGENT_APPROVAL_STATUS.EXPIRED
    )
    expect(result.current.decidingApprovalIds).toEqual([])

    act(() => {
      streamOptions?.onEvent(runFinished(3))
    })
  })

  it('断线重连：列表接口恢复待审批卡，已决的只展示不可操作', async () => {
    const { result } = await startRunWithApproval()
    // approval_required 已对齐一次列表（默认空）：等它落定，再让重连拿到两条记录
    await waitFor(() => {
      expect(result.current.approvals).toHaveLength(1)
    })
    listApprovalsMock.mockResolvedValue([
      {
        id: 'ap-0',
        runId: 'r-1',
        toolCallId: 'tc-0',
        status: AGENT_APPROVAL_STATUS.APPROVED,
        proposal: { tool: 'memory_write', risk: AGENT_TOOL_RISK.WRITE },
        decidedBy: 1,
        decidedAt: 't',
      },
      {
        id: 'ap-1',
        runId: 'r-1',
        toolCallId: 'tc-1',
        status: AGENT_APPROVAL_STATUS.PENDING,
        proposal: { tool: 'memory_write', risk: AGENT_TOOL_RISK.WRITE },
        expiresAt: '2030-01-01T00:00:00Z',
      },
    ])

    act(() => {
      streamOptions?.onStatus?.('open') // 首次连上：不对齐列表（事件到达时已对齐过一次）
    })
    const callsAfterFirstOpen = listApprovalsMock.mock.calls.length
    await waitFor(() => {
      expect(listApprovalsMock.mock.calls.length).toBe(callsAfterFirstOpen)
    })

    act(() => {
      streamOptions?.onStatus?.('reconnecting')
    })
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.RECONNECTING)

    act(() => {
      streamOptions?.onStatus?.('open') // 重连成功：同步审批状态
    })
    await waitFor(() => {
      expect(listApprovalsMock.mock.calls.length).toBe(callsAfterFirstOpen + 1)
      expect(result.current.approvals).toHaveLength(2)
    })
    expect(listApprovalsMock.mock.calls.at(-1)?.[0]).toBe('r-1')
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.WAITING_APPROVAL)
    expect(
      result.current.approvals.find((item) => item.id === 'ap-0')?.status
    ).toBe(AGENT_APPROVAL_STATUS.APPROVED)

    act(() => {
      streamOptions?.onEvent(runFinished(3))
    })
  })

  it('刷新恢复：服务端 run 仍在等审批时恢复待审批卡（本页未接事件流，不改阶段）', async () => {
    getSessionMock.mockResolvedValue({
      session: { id: 's-9', title: '历史会话' },
      messages: [],
      runs: [
        {
          id: 'r-9',
          sessionId: 's-9',
          status: AGENT_RUN_STATUS.WAITING_APPROVAL,
        },
      ],
    })
    listApprovalsMock.mockResolvedValue([
      {
        id: 'ap-9',
        runId: 'r-9',
        status: AGENT_APPROVAL_STATUS.PENDING,
        proposal: { tool: 'memory_write', risk: AGENT_TOOL_RISK.WRITE },
      },
    ])
    useAiChatSession.setState({ messages: [], agentSessionId: 's-9' })

    const { result } = renderHook(() => useAgentRun())

    await waitFor(() => {
      expect(listApprovalsMock).toHaveBeenCalledWith('r-9')
      expect(result.current.approvals).toHaveLength(1)
    })
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.IDLE)
    expect(result.current.run?.id).toBe('r-9')
  })

  it('终态后补 run 快照：token 与预算进入 run（时间线展示预算消耗）', async () => {
    getRunMock.mockResolvedValue({
      id: 'r-1',
      sessionId: 's-1',
      status: AGENT_RUN_STATUS.SUCCEEDED,
      tokenIn: 120,
      tokenOut: 30,
      budget: { maxTokens: 1000, maxToolCalls: 40 },
    })
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('你好')
    })

    act(() => {
      streamOptions?.onEvent(messageDelta(1, 'm-1', '完成'))
      streamOptions?.onEvent(runFinished(2))
    })

    await waitFor(() => {
      expect(result.current.run?.tokenIn).toBe(120)
      expect(result.current.run?.tokenOut).toBe(30)
      expect(result.current.run?.budget?.maxTokens).toBe(1000)
    })
  })
})

describe('useAgentRun 刷新恢复（getAgentSession）', () => {
  it('有会话 id 且本地消息为空：回填服务端历史，会话继续可用', async () => {
    getSessionMock.mockResolvedValue({
      session: { id: 's-9', title: '历史会话' },
      messages: [
        { role: 'user', content: '之前的问题' },
        { role: 'assistant', content: '之前的回答' },
      ],
      runs: [],
    })
    useAiChatSession.setState({ messages: [], agentSessionId: 's-9' })

    renderHook(() => useAgentRun())

    await waitFor(() => {
      expect(getSessionMock).toHaveBeenCalledWith('s-9')
      expect(useAiChatSession.getState().messages).toHaveLength(2)
    })
    const restored = useAiChatSession.getState().messages
    expect(restored[0]).toMatchObject({ from: 'user' })
    expect(restored[1].versions[0].content).toBe('之前的回答')
    expect(useAiChatSession.getState().agentSessionId).toBe('s-9')
  })

  it('刷新打断的悬挂气泡按服务端最新 run 终态收口', async () => {
    getSessionMock.mockResolvedValue({
      session: { id: 's-9', title: '历史会话' },
      messages: [],
      runs: [
        {
          id: 'r-9',
          sessionId: 's-9',
          status: AGENT_RUN_STATUS.SUCCEEDED,
        },
      ],
    })
    useAiChatSession.setState({
      agentSessionId: 's-9',
      messages: [
        {
          key: 'assistant-stale',
          from: 'assistant',
          versions: [{ id: 'assistant-stale-v1', content: '部分正文' }],
          status: 'streaming',
        },
      ],
    })

    renderHook(() => useAgentRun())

    await waitFor(() => {
      const [message] = useAiChatSession.getState().messages
      expect(message.status).toBe('complete')
      expect(message.runStatus).toBe(AGENT_RUN_STATUS.SUCCEEDED)
    })
    expect(useAiChatSession.getState().messages[0].versions[0].content).toBe('部分正文')
  })

  it('服务端会话已失效（404）：清掉本地会话 id，下次发送新建会话', async () => {
    getSessionMock.mockRejectedValue(new ApiError({ httpStatus: 404 }))
    useAiChatSession.setState({ messages: [], agentSessionId: 's-gone' })

    renderHook(() => useAgentRun())

    await waitFor(() => {
      expect(useAiChatSession.getState().agentSessionId).toBeNull()
    })
  })
})

/**
 * INT-2521 按 INT-2507 A5–A7 收窄后的口径：
 * - A5：浮窗最小化 / 展开整页 / 整页 ↔ 浮窗切换**不取消**在办 run，另一宿主重新挂载仍能看到
 *   流式输出与最终回复；
 * - A6：浮窗「关闭」与离开 `/ai-chat` 路由各发一次 `cancelAgentRun`；两宿主同开时卸载一侧
 *   不误取消另一侧；
 * - A7：StrictMode `mount → cleanup → mount` 不误取消；建 run 请求在途时离场，响应返回后
 *   补发取消（INT-2521 原逻辑保留）。
 */
describe('useAgentRun 宿主离场取消（INT-2521 收窄）', () => {
  /** 按真实宿主形态挂载：浮窗 `keep`（最小化 / 展开都是暂时卸载）、整页 `cancel`（离开路由） */
  function mountHost(host: 'page' | 'workbench', reason: 'cancel' | 'keep') {
    return renderHook(() => {
      useAgentRunHost(host, reason)
      return useAgentRun()
    })
  }

  it('A5：浮窗最小化 / 展开整页（keep 卸载）不取消，另一宿主重新挂载后仍能收到流式输出与最终回复', async () => {
    const float = mountHost('workbench', 'keep')
    await act(async () => {
      await float.result.current.send('帮我出一份长报告')
    })
    expect(float.result.current.phase).toBe(AGENT_RUN_PHASE.RUNNING)

    // 最小化 / 展开整页 = 浮窗会话组件卸载，但 run 应继续
    float.unmount()
    await act(async () => {
      await flushDetachGrace()
    })
    expect(cancelRunMock).not.toHaveBeenCalled()

    // 整页宿主重新挂载：订阅同一份 store，事件仍然落到同一条 assistant 气泡
    const page = mountHost('page', 'cancel')
    act(() => {
      streamOptions?.onEvent(messageDelta(1, 'm-1', '报告正文'))
      streamOptions?.onEvent(runFinished(2))
    })
    expect(page.result.current.phase).toBe(AGENT_RUN_PHASE.FINISHED)
    expect(useAiChatSession.getState().messages[1].versions[0].content).toBe('报告正文')
    expect(cancelRunMock).not.toHaveBeenCalled()
  })

  it('A6：浮窗「关闭」（最后一个宿主，cancel 语义）→ 取消一次并提示', async () => {
    const float = mountHost('workbench', 'keep')
    await act(async () => {
      await float.result.current.send('你好')
    })

    await act(async () => {
      useAgentRunStore.getState().detachHost('workbench', 'cancel')
      float.unmount()
      await flushDetachGrace()
    })

    expect(cancelRunMock).toHaveBeenCalledTimes(1)
    expect(cancelRunMock).toHaveBeenCalledWith('r-1')
    expect(toastInfoMock).toHaveBeenCalledWith(AGENT_RUN_UNMOUNT_CANCEL_COPY)
  })

  it('A6：离开 /ai-chat 路由（整页卸载，cancel 语义）→ 取消一次', async () => {
    const page = mountHost('page', 'cancel')
    await act(async () => {
      await page.result.current.send('你好')
    })

    await act(async () => {
      page.unmount()
      await flushDetachGrace()
    })

    expect(cancelRunMock).toHaveBeenCalledTimes(1)
    expect(cancelRunMock).toHaveBeenCalledWith('r-1')
  })

  it('A6：两宿主同开时卸载一侧不误取消另一侧（关闭浮窗，整页仍开着）', async () => {
    const page = mountHost('page', 'cancel')
    const float = mountHost('workbench', 'keep')
    await act(async () => {
      await page.result.current.send('你好')
    })

    await act(async () => {
      useAgentRunStore.getState().detachHost('workbench', 'cancel')
      float.unmount()
      await flushDetachGrace()
    })

    expect(cancelRunMock).not.toHaveBeenCalled()
    expect(page.result.current.phase).toBe(AGENT_RUN_PHASE.RUNNING)
  })

  it('A6：重复关闭（两次 cancel 语义离场）全局只发一次 cancelAgentRun', async () => {
    mountHost('workbench', 'keep')
    const float = mountHost('workbench', 'keep')
    await act(async () => {
      await float.result.current.send('你好')
    })

    await act(async () => {
      useAgentRunStore.getState().detachHost('workbench', 'cancel')
      useAgentRunStore.getState().detachHost('workbench', 'cancel')
      float.unmount()
      await flushDetachGrace()
    })

    expect(cancelRunMock).toHaveBeenCalledTimes(1)
  })

  it('A7：StrictMode mount → cleanup → mount 不误取消在办 run', async () => {
    const float = mountHost('workbench', 'keep')
    await act(async () => {
      await float.result.current.send('你好')
    })
    // 最小化：浮窗作为唯一宿主正常离场（keep），在办 run 保留
    float.unmount()

    // 整页在 StrictMode 下首挂：cleanup 会以 cancel 语义注销，但同一提交内重新 attach
    renderHook(() => useAgentRunHost('page', 'cancel'), { wrapper: StrictMode })
    await act(async () => {
      await flushDetachGrace()
    })

    expect(cancelRunMock).not.toHaveBeenCalled()
    expect(useAgentRunStore.getState().phase).toBe(AGENT_RUN_PHASE.RUNNING)
  })

  it('A7：建 run 请求在途时按 cancel 语义离场 → 响应返回后补发取消一次（不留孤儿 run）', async () => {
    let resolveRun: ((run: AgentRun) => void) | null = null
    createRunMock.mockImplementation(
      () =>
        new Promise<AgentRun>((resolve) => {
          resolveRun = resolve
        })
    )
    const page = mountHost('page', 'cancel')
    let pending!: Promise<void>
    await act(async () => {
      pending = page.result.current.send('你好')
    })

    // 此时 run 还没落库，没有可取消的对象
    await act(async () => {
      page.unmount()
      await flushDetachGrace()
    })
    expect(cancelRunMock).not.toHaveBeenCalled()

    await act(async () => {
      resolveRun?.({ id: 'r-late', sessionId: 's-1', status: AGENT_RUN_STATUS.RUNNING })
      await pending
      await flushDetachGrace()
    })

    expect(cancelRunMock).toHaveBeenCalledTimes(1)
    expect(cancelRunMock).toHaveBeenCalledWith('r-late')
    expect(toastInfoMock).toHaveBeenCalledWith(AGENT_RUN_UNMOUNT_CANCEL_COPY)
  })

  it('无在办 run 时离场不发取消', async () => {
    const page = mountHost('page', 'cancel')
    page.unmount()

    await act(async () => {
      await flushDetachGrace()
    })

    expect(cancelRunMock).not.toHaveBeenCalled()
    expect(toastInfoMock).not.toHaveBeenCalled()
  })

  it('run 已终态时离场不发取消', async () => {
    const page = mountHost('page', 'cancel')
    await act(async () => {
      await page.result.current.send('你好')
    })
    act(() => {
      streamOptions?.onEvent(runFinished(1))
    })
    expect(page.result.current.phase).toBe(AGENT_RUN_PHASE.FINISHED)

    page.unmount()
    await act(async () => {
      await flushDetachGrace()
    })

    expect(cancelRunMock).not.toHaveBeenCalled()
    expect(toastInfoMock).not.toHaveBeenCalled()
  })
})

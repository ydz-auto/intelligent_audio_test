/**
 * Auto 模式 run store 单测（INT-2474 §9.4）。
 *
 * 覆盖：
 * - 发起 Auto run 时 mode / 收紧预算如何传给 API；普通对话不受影响；
 * - auto_step → 进度快照 + 时间线；
 * - run_paused → 暂停事实 + run / phase 转 WAITING_APPROVAL；
 * - resumeAuto：成功（run 快照 + RUNNING）、409 有待审批提案（提示先处理审批卡）、
 *   409 已不在暂停态（刷新快照后撤掉暂停面板）；
 * - 终态（BUDGET_EXCEEDED / 熔断）清暂停点、保留进度供收口展示。
 *
 * API 层全部替身；真实栈证据见交付评论。
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AGENT_AUTO_COPY,
  AGENT_EVENT_TYPE,
  AGENT_RUN_PAUSE_REASON,
  AGENT_RUN_STATUS,
  type AgentRun,
  type AgentRunEvent,
} from '@/domain/models/agent'
import {
  AGENT_RUN_PHASE,
  useAgentRun,
} from '@/application/agent/use-agent-run'
import { useAgentRunStore } from '@/application/agent/agent-run-store'
import {
  createAgentRun,
  createAgentSession,
  getAgentRun,
  getAgentSession,
  listAgentApprovals,
  resumeAgentRun,
  subscribeAgentRunEvents,
} from '@/infrastructure/api/agentApi'
import type { SubscribeAgentRunEventsOptions } from '@/infrastructure/api/agentApi'
import { ApiError } from '@/infrastructure/api/api-error'
import { useAiChatSession } from '@/infrastructure/stores/aiChatSessionStore'

vi.mock('sonner', () => ({
  toast: { info: vi.fn(), error: vi.fn(), success: vi.fn() },
}))

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
    resumeAgentRun: vi.fn(),
  }
})

const createSessionMock = vi.mocked(createAgentSession)
const createRunMock = vi.mocked(createAgentRun)
const subscribeMock = vi.mocked(subscribeAgentRunEvents)
const getRunMock = vi.mocked(getAgentRun)
const getSessionMock = vi.mocked(getAgentSession)
const listApprovalsMock = vi.mocked(listAgentApprovals)
const resumeMock = vi.mocked(resumeAgentRun)

let streamOptions: SubscribeAgentRunEventsOptions | null = null

const AUTO_RUN: AgentRun = {
  id: 'r-1',
  sessionId: 's-1',
  status: AGENT_RUN_STATUS.RUNNING,
  mode: 'auto',
}

function autoStep(sequence: number, step = 1): AgentRunEvent {
  return {
    type: AGENT_EVENT_TYPE.AUTO_STEP,
    runId: 'r-1',
    sequence,
    timestamp: 't',
    progress: {
      step,
      phase: 'step',
      goal: '把回归测试全跑一遍',
      plan: '先读用例，再起任务',
      usage: {
        rounds: step,
        toolCalls: step * 2,
        tokens: 1000 * step,
        elapsedSeconds: 30 * step,
        outputBytes: 0,
      },
      limits: { maxRounds: 60, maxToolCalls: 120, maxDurationSeconds: 1800 },
      ratio: 0.05,
      consecutiveFailures: 0,
      artifactCount: 0,
      artifacts: [],
    },
  }
}

function messageDelta(
  sequence: number,
  messageId: string,
  delta: string
): AgentRunEvent {
  return {
    type: AGENT_EVENT_TYPE.MESSAGE_DELTA,
    runId: 'r-1',
    sequence,
    timestamp: 't',
    messageId,
    delta,
  }
}

function runPaused(sequence: number): AgentRunEvent {
  return {
    type: AGENT_EVENT_TYPE.RUN_PAUSED,
    runId: 'r-1',
    sequence,
    timestamp: '2026-11-14T10:01:00Z',
    pause: {
      reason: AGENT_RUN_PAUSE_REASON.BUDGET_THRESHOLD,
      usage: {
        rounds: 48,
        toolCalls: 96,
        tokens: 400000,
        elapsedSeconds: 1000,
        outputBytes: 0,
      },
      limits: { maxRounds: 60, maxToolCalls: 120 },
      ratio: 0.8,
      consecutiveFailures: 0,
      policy: { budgetRatio: 0.8, consecutiveFailures: 2 },
    },
  }
}

function resetSharedState() {
  window.localStorage.clear()
  useAgentRunStore.getState().reset()
  useAgentRunStore.getState().detachHost('page', 'keep')
  useAgentRunStore.getState().detachHost('workbench', 'keep')
  useAiChatSession.setState({ messages: [], agentSessionId: null, agentRunId: null })
  window.localStorage.clear()
}

beforeEach(() => {
  streamOptions = null
  resetSharedState()
  createSessionMock.mockResolvedValue({ id: 's-1', title: '会话' })
  createRunMock.mockResolvedValue(AUTO_RUN)
  subscribeMock.mockImplementation((_runId, options) => {
    streamOptions = options
    return () => undefined
  })
  getSessionMock.mockResolvedValue({
    session: { id: 's-1', title: '会话' },
    messages: [],
    runs: [],
  })
  listApprovalsMock.mockResolvedValue([])
  getRunMock.mockResolvedValue(AUTO_RUN)
  resumeMock.mockResolvedValue(AUTO_RUN)
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('Auto 发起', () => {
  it('Auto：mode=auto + 收紧预算传给 API，run 快照带 mode', async () => {
    const { result } = renderHook(() => useAgentRun())

    await act(async () => {
      await result.current.send('把回归测试全跑一遍', {
        mode: 'auto',
        budget: { maxRounds: 20, maxDurationSeconds: 600 },
      })
    })

    expect(createRunMock.mock.calls[0][1]).toEqual({
      message: '把回归测试全跑一遍',
      mode: 'auto',
      budget: { maxRounds: 20, maxDurationSeconds: 600 },
    })
    expect(result.current.run?.mode).toBe('auto')
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.RUNNING)
  })

  it('普通对话：不带 mode / budget（Auto 关闭不影响普通对话）', async () => {
    createRunMock.mockResolvedValue({
      id: 'r-1',
      sessionId: 's-1',
      status: AGENT_RUN_STATUS.RUNNING,
    })
    const { result } = renderHook(() => useAgentRun())

    await act(async () => {
      await result.current.send('今天天气')
    })

    expect(createRunMock.mock.calls[0][1]).toEqual({ message: '今天天气' })
    expect(result.current.run?.mode).toBeUndefined()
  })
})

describe('Auto 进度与暂停', () => {
  it('run_started 带 pause_policy → 策略可展示', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('目标', { mode: 'auto' })
    })

    act(() => {
      streamOptions?.onEvent({
        type: AGENT_EVENT_TYPE.RUN_STARTED,
        runId: 'r-1',
        sequence: 1,
        timestamp: 't',
        status: AGENT_RUN_STATUS.RUNNING,
        mode: 'auto',
        pausePolicy: { budgetRatio: 0.8, consecutiveFailures: 2 },
      })
    })

    expect(result.current.autoPausePolicy).toEqual({
      budgetRatio: 0.8,
      consecutiveFailures: 2,
    })
  })

  it('auto_step → 进度快照 + 时间线条目（含步序号与比例）', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('目标', { mode: 'auto' })
    })

    act(() => {
      streamOptions?.onEvent(autoStep(1, 1))
      streamOptions?.onEvent(autoStep(2, 2))
    })

    expect(result.current.autoProgress?.step).toBe(2)
    expect(result.current.autoProgress?.goal).toBe('把回归测试全跑一遍')
    const steps = result.current.timeline.filter(
      (entry) => entry.kind === 'auto_step'
    )
    expect(steps).toHaveLength(2)
    expect(steps[1].step).toBe(2)
    expect(steps[1].ratio).toBe(0.05)
    // 进度事件不改生命周期阶段
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.RUNNING)
  })

  it('run_paused → 暂停事实 + run / phase 转 WAITING_APPROVAL', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('目标', { mode: 'auto' })
    })

    act(() => {
      streamOptions?.onEvent(autoStep(1, 48))
      streamOptions?.onEvent(runPaused(2))
    })

    expect(result.current.autoPause?.reason).toBe(
      AGENT_RUN_PAUSE_REASON.BUDGET_THRESHOLD
    )
    expect(result.current.autoPause?.ratio).toBe(0.8)
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.WAITING_APPROVAL)
    expect(result.current.run?.status).toBe(AGENT_RUN_STATUS.WAITING_APPROVAL)
    // 暂停点用量回写到进度（面板展示「停在哪一项」）
    expect(result.current.autoProgress?.usage.rounds).toBe(48)
    expect(result.current.autoProgress?.pauseReason).toBe(
      AGENT_RUN_PAUSE_REASON.BUDGET_THRESHOLD
    )
    // 暂停时在途气泡收口（P3-2）：不再滞留「正在回复...」，也不挂等待审批徽标（P3-1）
    const [message] = useAiChatSession.getState().messages.filter(
      (item) => item.from === 'assistant'
    )
    expect(message.status).toBe('complete')
    expect(message.runStatus).toBeUndefined()
    expect(message.versions[0].content).toBe(AGENT_AUTO_COPY.phasePendingResume)
  })
})

describe('Auto 继续', () => {
  it('resume 成功 → run 回到 RUNNING，暂停面板撤掉', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('目标', { mode: 'auto' })
    })
    act(() => {
      streamOptions?.onEvent(autoStep(1, 48))
      streamOptions?.onEvent(runPaused(2))
    })

    await act(async () => {
      const failure = await result.current.resumeAuto()
      expect(failure).toBeNull()
    })

    expect(resumeMock).toHaveBeenCalledWith('r-1')
    expect(result.current.autoPause).toBeNull()
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.RUNNING)
    expect(result.current.run?.status).toBe(AGENT_RUN_STATUS.RUNNING)
  })

  it('resume 409 且仍有待审批提案 → 提示先处理审批卡，不撤暂停点', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('目标', { mode: 'auto' })
    })
    act(() => {
      streamOptions?.onEvent(autoStep(1, 48))
      streamOptions?.onEvent(runPaused(2))
    })
    resumeMock.mockRejectedValue(
      new ApiError({
        httpStatus: 409,
        message: '',
        detail: '仍有待审批提案：请先处理审批单，再继续',
      })
    )
    listApprovalsMock.mockResolvedValue([
      {
        id: 'ap-1',
        runId: 'r-1',
        status: 'PENDING',
        proposal: { tool: 'task_run', risk: 'WRITE' },
      },
    ])

    let failure: string | null = null
    await act(async () => {
      failure = await result.current.resumeAuto()
    })

    expect(failure).toBe(AGENT_AUTO_COPY.resumeNeedsApproval)
    expect(result.current.autoPause).not.toBeNull()
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.WAITING_APPROVAL)
  })

  it('resume 409 且已不在暂停态 → 刷新快照，撤掉暂停面板并给服务端原因', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('目标', { mode: 'auto' })
    })
    act(() => {
      streamOptions?.onEvent(autoStep(1, 48))
      streamOptions?.onEvent(runPaused(2))
    })
    resumeMock.mockRejectedValue(
      new ApiError({
        httpStatus: 409,
        message: '',
        detail: 'run 当前不在暂停态（可能正在执行或已继续）',
      })
    )
    listApprovalsMock.mockResolvedValue([])
    getRunMock.mockResolvedValue({
      ...AUTO_RUN,
      status: AGENT_RUN_STATUS.RUNNING,
    })

    let failure: string | null = null
    await act(async () => {
      failure = await result.current.resumeAuto()
    })

    expect(failure).toBe('run 当前不在暂停态（可能正在执行或已继续）')
    expect(result.current.autoPause).toBeNull()
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.RUNNING)
  })

  it('resume 竞态：事件流先收口时不被 resume 返回的旧快照拉回 RUNNING', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('目标', { mode: 'auto' })
    })
    act(() => {
      streamOptions?.onEvent(autoStep(1, 48))
      streamOptions?.onEvent(runPaused(2))
    })
    // 短任务：resume 请求在途期间 run 已经跑完，事件流先一步收口
    resumeMock.mockImplementation(async () => {
      act(() => {
        streamOptions?.onEvent({
          type: AGENT_EVENT_TYPE.RUN_FINISHED,
          runId: 'r-1',
          sequence: 3,
          timestamp: 't',
          status: AGENT_RUN_STATUS.SUCCEEDED,
        })
      })
      return { ...AUTO_RUN, status: AGENT_RUN_STATUS.RUNNING }
    })

    let failure: string | null = null
    await act(async () => {
      failure = await result.current.resumeAuto()
    })

    expect(failure).toBeNull()
    expect(result.current.run?.status).toBe(AGENT_RUN_STATUS.SUCCEEDED)
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.FINISHED)
  })

  it('run_resumed 事件到达后暂停点解除（同一暂停点不再触发）', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('目标', { mode: 'auto' })
    })
    act(() => {
      streamOptions?.onEvent(autoStep(1, 48))
      streamOptions?.onEvent(runPaused(2))
    })

    act(() => {
      streamOptions?.onEvent({
        type: AGENT_EVENT_TYPE.RUN_RESUMED,
        runId: 'r-1',
        sequence: 3,
        timestamp: 't',
        pauseReason: AGENT_RUN_PAUSE_REASON.BUDGET_THRESHOLD,
        ackedBudgetPause: true,
      })
    })

    expect(result.current.autoPause).toBeNull()
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.RUNNING)
    expect(
      result.current.timeline.some((entry) => entry.kind === 'run_resumed')
    ).toBe(true)
  })
})

describe('Auto 终态', () => {
  it('BUDGET_EXCEEDED → 终态徽标不显示成功，暂停点清空但进度保留', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('目标', { mode: 'auto' })
    })
    act(() => {
      streamOptions?.onEvent(autoStep(1, 1))
      streamOptions?.onEvent(runPaused(2))
      streamOptions?.onEvent({
        type: AGENT_EVENT_TYPE.RUN_FINISHED,
        runId: 'r-1',
        sequence: 3,
        timestamp: 't',
        status: AGENT_RUN_STATUS.BUDGET_EXCEEDED,
        error: 'BUDGET_EXCEEDED',
      })
    })

    expect(result.current.phase).toBe(AGENT_RUN_PHASE.FINISHED)
    expect(result.current.run?.status).toBe(AGENT_RUN_STATUS.BUDGET_EXCEEDED)
    expect(result.current.autoPause).toBeNull()
    expect(result.current.autoProgress?.step).toBe(1)
  })

  it('熔断：ERROR(CONSECUTIVE_TOOL_FAILURES) 直接落 FAILED（终态帧被关流时也不丢）', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('目标', { mode: 'auto' })
    })
    act(() => {
      streamOptions?.onEvent(autoStep(1, 3))
      // 后端先发 error 帧再发 run_finished；error 帧会关流，终态帧可能收不到
      streamOptions?.onEvent({
        type: AGENT_EVENT_TYPE.ERROR,
        runId: 'r-1',
        sequence: 2,
        timestamp: 't',
        errorCode: 'CONSECUTIVE_TOOL_FAILURES',
        errorMessage: '连续工具失败达到熔断阈值，停止自动重试',
      })
    })

    expect(result.current.run?.status).toBe(AGENT_RUN_STATUS.FAILED)
    expect(result.current.run?.error).toBe('CONSECUTIVE_TOOL_FAILURES')
    // 熔断是 Auto 的明确终态（面板给「Auto 已熔断停止」），不再落通用 ERROR 阶段
    expect(result.current.phase).toBe(AGENT_RUN_PHASE.FINISHED)
    // 气泡按 Auto 熔断口径收口，不复用通用「Agent 运行失败，请重试」（P3-5）
    const [message] = useAiChatSession.getState().messages.filter(
      (item) => item.from === 'assistant'
    )
    expect(message.status).toBe('complete')
    expect(message.runStatus).toBe(AGENT_RUN_STATUS.FAILED)
    expect(message.versions[0].content).toContain(AGENT_AUTO_COPY.circuitTitle)
  })

  it('熔断：ERROR 收口保留已流式产出的正文（代码审计 P2-2）', async () => {
    const narrative = '已完成的正文片段（必须保留）'
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('目标', { mode: 'auto' })
    })
    act(() => {
      streamOptions?.onEvent(autoStep(1, 2))
      streamOptions?.onEvent(messageDelta(2, 'm-1', narrative))
      streamOptions?.onEvent({
        type: AGENT_EVENT_TYPE.ERROR,
        runId: 'r-1',
        sequence: 3,
        timestamp: 't',
        errorCode: 'CONSECUTIVE_TOOL_FAILURES',
        errorMessage: '连续工具失败达到熔断阈值，停止自动重试',
      })
    })

    // 熔断是明确终态：徽标 / 面板照常熔断，但已产出的正文不能被终态标题整段替换
    expect(result.current.run?.status).toBe(AGENT_RUN_STATUS.FAILED)
    const [message] = useAiChatSession.getState().messages.filter(
      (item) => item.from === 'assistant'
    )
    expect(message.runStatus).toBe(AGENT_RUN_STATUS.FAILED)
    expect(message.versions[0].content).toBe(narrative)
  })

  it('熔断（run_finished FAILED）保留错误原因', async () => {
    const { result } = renderHook(() => useAgentRun())
    await act(async () => {
      await result.current.send('目标', { mode: 'auto' })
    })
    act(() => {
      streamOptions?.onEvent(autoStep(1, 3))
      streamOptions?.onEvent({
        type: AGENT_EVENT_TYPE.RUN_FINISHED,
        runId: 'r-1',
        sequence: 2,
        timestamp: 't',
        status: AGENT_RUN_STATUS.FAILED,
        error: 'CONSECUTIVE_TOOL_FAILURES',
      })
    })

    expect(result.current.run?.status).toBe(AGENT_RUN_STATUS.FAILED)
    expect(result.current.run?.error).toBe('CONSECUTIVE_TOOL_FAILURES')
  })
})

/**
 * 刷新恢复后的「继续」（INT-2477 UX 审计 P2）：本页没有事件流，继续成功后必须
 * 跟随到服务端真实终态，不能把界面永久停在「正在收集步骤进度…」与旧的暂停占位文案。
 */
describe('刷新恢复后的 Auto 继续（P2）', () => {
  const PAUSED_AUTO_RUN: AgentRun = {
    id: 'r-9',
    sessionId: 's-9',
    status: AGENT_RUN_STATUS.WAITING_APPROVAL,
    mode: 'auto',
  }

  function seedRestoredPause() {
    getSessionMock.mockResolvedValue({
      session: { id: 's-9', title: '历史会话' },
      messages: [],
      runs: [PAUSED_AUTO_RUN],
    })
    listApprovalsMock.mockResolvedValue([])
    useAiChatSession.setState({
      agentSessionId: 's-9',
      messages: [
        {
          key: 'assistant-stale',
          from: 'assistant',
          versions: [{ id: 'assistant-stale-v1', content: '' }],
          status: 'loading',
        },
      ],
    })
  }

  it('恢复暂停态：暂停不是「等待审批」，气泡不挂等待审批徽标（P3-1）', async () => {
    seedRestoredPause()
    const { result } = renderHook(() => useAgentRun())

    await waitFor(() => {
      expect(result.current.autoPause).not.toBeNull()
    })
    const [message] = useAiChatSession.getState().messages
    expect(message.status).toBe('complete')
    expect(message.runStatus).toBeUndefined()
    expect(message.versions[0].content).toBe(AGENT_AUTO_COPY.restoredPaused)
  })

  it('继续 → 轮询到 SUCCEEDED：气泡换成 Auto 终态，autoTracking 收口', async () => {
    seedRestoredPause()
    resumeMock.mockResolvedValue({
      ...PAUSED_AUTO_RUN,
      status: AGENT_RUN_STATUS.RUNNING,
    })
    getRunMock.mockResolvedValue({
      ...PAUSED_AUTO_RUN,
      status: AGENT_RUN_STATUS.SUCCEEDED,
    })
    const { result } = renderHook(() => useAgentRun())
    await waitFor(() => {
      expect(result.current.autoPause).not.toBeNull()
    })

    await act(async () => {
      expect(await result.current.resumeAuto()).toBeNull()
    })
    // 继续后立刻撤掉暂停占位文案，面板进入「等待服务端结果」
    expect(result.current.autoTracking).toBe(true)
    expect(useAiChatSession.getState().messages[0].versions[0].content).toBe(
      AGENT_AUTO_COPY.restoredResuming
    )

    await waitFor(
      () => {
        expect(result.current.autoTracking).toBe(false)
        expect(result.current.run?.status).toBe(AGENT_RUN_STATUS.SUCCEEDED)
        expect(result.current.phase).toBe(AGENT_RUN_PHASE.FINISHED)
        expect(useAiChatSession.getState().messages[0].versions[0].content).toBe(
          AGENT_AUTO_COPY.finishedTitle
        )
      },
      { timeout: 8_000 }
    )
    expect(result.current.autoPause).toBeNull()
  })

  it('暂停气泡已在前端收口（complete）时，继续后仍撤掉暂停文案并跟到终态（P2 兜底）', async () => {
    getSessionMock.mockResolvedValue({
      session: { id: 's-9', title: '历史会话' },
      messages: [],
      runs: [PAUSED_AUTO_RUN],
    })
    listApprovalsMock.mockResolvedValue([])
    // 刷新前 RUN_PAUSED 已把气泡落成 complete + 暂停文案（P3-2）：
    // reconcile 找不到「进行中」气泡，仍要能记下这一条并在继续后更新
    useAiChatSession.setState({
      agentSessionId: 's-9',
      messages: [
        {
          key: 'assistant-settled',
          from: 'assistant',
          versions: [
            { id: 'assistant-settled-v1', content: AGENT_AUTO_COPY.phasePendingResume },
          ],
          status: 'complete',
        },
      ],
    })
    resumeMock.mockResolvedValue({
      ...PAUSED_AUTO_RUN,
      status: AGENT_RUN_STATUS.RUNNING,
    })
    getRunMock.mockResolvedValue({
      ...PAUSED_AUTO_RUN,
      status: AGENT_RUN_STATUS.SUCCEEDED,
    })
    const { result } = renderHook(() => useAgentRun())
    await waitFor(() => {
      expect(result.current.autoPause).not.toBeNull()
    })

    await act(async () => {
      expect(await result.current.resumeAuto()).toBeNull()
    })
    expect(useAiChatSession.getState().messages[0].versions[0].content).toBe(
      AGENT_AUTO_COPY.restoredResuming
    )

    await waitFor(
      () => {
        expect(useAiChatSession.getState().messages[0].versions[0].content).toBe(
          AGENT_AUTO_COPY.finishedTitle
        )
      },
      { timeout: 8_000 }
    )
  })

  it('暂停气泡已有正文 → 刷新 → 继续 → 终态：正文保留，终态落 runStatus（代码审计 P2-1）', async () => {
    const narrative = '已完成前两步：读取用例 12 条，检索任务 3 个。等待继续。'
    getSessionMock.mockResolvedValue({
      session: { id: 's-9', title: '历史会话' },
      messages: [],
      runs: [PAUSED_AUTO_RUN],
    })
    listApprovalsMock.mockResolvedValue([])
    useAiChatSession.setState({
      agentSessionId: 's-9',
      messages: [
        {
          key: 'auto-user',
          from: 'user',
          versions: [{ id: 'auto-user-v1', content: '把回归测试全跑一遍' }],
          status: 'complete',
        },
        {
          key: 'auto-paused',
          from: 'assistant',
          versions: [{ id: 'auto-paused-v1', content: narrative }],
          status: 'complete',
          startedAt: Date.now() - 60_000,
        },
      ],
    })
    resumeMock.mockResolvedValue({
      ...PAUSED_AUTO_RUN,
      status: AGENT_RUN_STATUS.RUNNING,
    })
    getRunMock.mockResolvedValue({
      ...PAUSED_AUTO_RUN,
      status: AGENT_RUN_STATUS.SUCCEEDED,
    })
    const { result } = renderHook(() => useAgentRun())
    await waitFor(() => {
      expect(result.current.autoPause).not.toBeNull()
    })
    const pausedBubble = () =>
      useAiChatSession
        .getState()
        .messages.find((message) => message.key === 'auto-paused')!

    await act(async () => {
      expect(await result.current.resumeAuto()).toBeNull()
    })
    // 继续时不把已有正文换成「已继续运行，正在等待服务端结果…」占位
    expect(pausedBubble().versions[0].content).toBe(narrative)

    await waitFor(
      () => {
        expect(result.current.autoTracking).toBe(false)
        // 终态由 runStatus 徽标 + 面板终态块表达，正文不得被终态标题覆盖
        expect(pausedBubble().runStatus).toBe(AGENT_RUN_STATUS.SUCCEEDED)
        expect(pausedBubble().versions[0].content).toBe(narrative)
      },
      { timeout: 8_000 }
    )
  })

  it('刷新前本轮没有气泡：不覆盖上一轮正常对话的回答（代码审计 P2-1 兜底）', async () => {
    const previousAnswer = '上一轮正常对话的回答。'
    getSessionMock.mockResolvedValue({
      session: { id: 's-9', title: '历史会话' },
      messages: [],
      runs: [PAUSED_AUTO_RUN],
    })
    listApprovalsMock.mockResolvedValue([])
    // 历史 [user 问题, assistant 回答, user Auto 目标]：暂停 run 在本端没有气泡，
    // 兜底不能把上一轮回答认成 Auto 气泡（继续到终态会把它整段覆盖）
    useAiChatSession.setState({
      agentSessionId: 's-9',
      messages: [
        {
          key: 'previous-user',
          from: 'user',
          versions: [{ id: 'previous-user-v1', content: '上一轮问题' }],
          status: 'complete',
        },
        {
          key: 'previous-answer',
          from: 'assistant',
          versions: [{ id: 'previous-answer-v1', content: previousAnswer }],
          status: 'complete',
        },
        {
          key: 'auto-user',
          from: 'user',
          versions: [{ id: 'auto-user-v1', content: '把回归测试全跑一遍' }],
          status: 'complete',
        },
      ],
    })
    resumeMock.mockResolvedValue({
      ...PAUSED_AUTO_RUN,
      status: AGENT_RUN_STATUS.RUNNING,
    })
    getRunMock.mockResolvedValue({
      ...PAUSED_AUTO_RUN,
      status: AGENT_RUN_STATUS.SUCCEEDED,
    })
    const { result } = renderHook(() => useAgentRun())
    await waitFor(() => {
      expect(result.current.autoPause).not.toBeNull()
    })

    await act(async () => {
      expect(await result.current.resumeAuto()).toBeNull()
    })
    await waitFor(
      () => {
        expect(result.current.autoTracking).toBe(false)
        expect(result.current.run?.status).toBe(AGENT_RUN_STATUS.SUCCEEDED)
      },
      { timeout: 8_000 }
    )

    const messages = useAiChatSession.getState().messages
    expect(messages).toHaveLength(3)
    expect(messages[1].versions[0].content).toBe(previousAnswer)
    expect(messages[1].runStatus).toBeUndefined()
  })

  it('续跑后再次暂停：恢复暂停面板并停止轮询（P3-1）', async () => {
    seedRestoredPause()
    resumeMock.mockResolvedValue({
      ...PAUSED_AUTO_RUN,
      status: AGENT_RUN_STATUS.RUNNING,
    })
    // 续跑后连续失败阈值再次触发：服务端又落 WAITING_APPROVAL
    getRunMock.mockResolvedValue(PAUSED_AUTO_RUN)
    const { result } = renderHook(() => useAgentRun())
    await waitFor(() => {
      expect(result.current.autoPause).not.toBeNull()
    })

    await act(async () => {
      expect(await result.current.resumeAuto()).toBeNull()
    })
    expect(result.current.autoTracking).toBe(true)

    await waitFor(
      () => {
        // 不能一直挂在「正在等待服务端结果…」：暂停面板与继续入口恢复，轮询停止
        expect(result.current.autoTracking).toBe(false)
        expect(result.current.autoPause).not.toBeNull()
        expect(result.current.run?.status).toBe(
          AGENT_RUN_STATUS.WAITING_APPROVAL
        )
        expect(useAiChatSession.getState().messages[0].versions[0].content).toBe(
          AGENT_AUTO_COPY.restoredPaused
        )
      },
      { timeout: 8_000 }
    )
  })

  it('继续 → 轮询到 BUDGET_EXCEEDED：气泡与 run 状态都是超预算口径，不误导为成功', async () => {
    seedRestoredPause()
    resumeMock.mockResolvedValue({
      ...PAUSED_AUTO_RUN,
      status: AGENT_RUN_STATUS.RUNNING,
    })
    getRunMock.mockResolvedValue({
      ...PAUSED_AUTO_RUN,
      status: AGENT_RUN_STATUS.BUDGET_EXCEEDED,
      error: 'BUDGET_EXCEEDED',
    })
    const { result } = renderHook(() => useAgentRun())
    await waitFor(() => {
      expect(result.current.autoPause).not.toBeNull()
    })

    await act(async () => {
      expect(await result.current.resumeAuto()).toBeNull()
    })

    await waitFor(
      () => {
        expect(result.current.run?.status).toBe(
          AGENT_RUN_STATUS.BUDGET_EXCEEDED
        )
        const [message] = useAiChatSession.getState().messages
        expect(message.runStatus).toBe(AGENT_RUN_STATUS.BUDGET_EXCEEDED)
        expect(message.versions[0].content).toContain(
          AGENT_AUTO_COPY.budgetExceededTitle
        )
      },
      { timeout: 8_000 }
    )
  })
})

/**
 * Auto 模式 API / DTO 契约单测（INT-2474 §9.4）。
 *
 * 覆盖：
 * - 发起 run 的请求体：Auto 带 `mode=auto` + 收紧预算（蛇形键、只带 >0 维度）；
 *   普通对话保持 `{message}` 单口径（Auto 关闭不影响普通对话）；
 * - `POST /agent/runs/{id}/resume` 路径与快照解析（RunResponse.mode）；
 * - SSE 帧 → 领域事件：run_started（mode / pause_policy）、auto_step、run_paused、
 *   run_resumed。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  AGENT_EVENT_TYPE,
  AGENT_RUN_PAUSE_REASON,
  AGENT_RUN_STATUS,
  type AgentRunEvent,
} from '@/domain/models/agent'
import {
  AGENT_API_PATHS,
  createAgentRun,
  resumeAgentRun,
} from '@/infrastructure/api/agentApi'
import { toAgentRunEvent } from '@/infrastructure/dto/agent.dto'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function parseBody(fetchMock: ReturnType<typeof vi.fn>): unknown {
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
  return JSON.parse(String(init.body))
}

afterEach(() => {
  vi.unstubAllGlobals()
  authTokenStore.clear()
})

describe('Agent API：Auto 模式请求体', () => {
  it('Auto：带 mode=auto 与收紧预算（分钟→秒、MB→字节由上层完成，这里只验蛇形键）', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ run: { id: 'r-1', session_id: 's-1', status: 'RUNNING', mode: 'auto' }, created: true })
    )
    vi.stubGlobal('fetch', fetchMock)

    const run = await createAgentRun(
      's-1',
      {
        message: '把回归测试全跑一遍',
        mode: 'auto',
        budget: {
          maxRounds: 20,
          maxToolCalls: 40,
          maxTokens: 100000,
          maxDurationSeconds: 600,
          maxOutputBytes: 5 * 1024 * 1024,
        },
      },
      'idem-1'
    )

    expect(run.mode).toBe('auto')
    expect(parseBody(fetchMock)).toEqual({
      message: '把回归测试全跑一遍',
      mode: 'auto',
      budget: {
        max_rounds: 20,
        max_tool_calls: 40,
        max_tokens: 100000,
        max_duration_seconds: 600,
        max_output_bytes: 5 * 1024 * 1024,
      },
    })
  })

  it('普通对话：请求体仍只有 message（不带 mode / budget）', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ run: { id: 'r-2', session_id: 's-1', status: 'RUNNING' }, created: true })
    )
    vi.stubGlobal('fetch', fetchMock)

    const run = await createAgentRun('s-1', { message: '你好' }, 'idem-2')

    expect(run.mode).toBeUndefined()
    expect(parseBody(fetchMock)).toEqual({ message: '你好' })
  })

  it('预算只带显式 >0 的维度（0 / 负数视为不覆盖）', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ run: { id: 'r-3', session_id: 's-1', status: 'RUNNING' }, created: true })
    )
    vi.stubGlobal('fetch', fetchMock)

    await createAgentRun(
      's-1',
      { message: '目标', mode: 'auto', budget: { maxRounds: 5, maxTokens: 0 } },
      'idem-3'
    )

    expect(parseBody(fetchMock)).toEqual({
      message: '目标',
      mode: 'auto',
      budget: { max_rounds: 5 },
    })
  })

  it('resume：POST /agent/runs/{id}/resume 并解析 RunResponse', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ id: 'r-9', session_id: 's-1', status: 'RUNNING', mode: 'auto' })
    )
    vi.stubGlobal('fetch', fetchMock)

    const run = await resumeAgentRun('r-9')

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`/api/v1${AGENT_API_PATHS.runResume('r-9')}`)
    expect(init.method).toBe('POST')
    expect(run).toMatchObject({
      id: 'r-9',
      status: AGENT_RUN_STATUS.RUNNING,
      mode: 'auto',
    })
  })
})

describe('Agent DTO：Auto 事件转换', () => {
  it('run_started：带 mode 与 pause_policy（Auto 启动即展示暂停规则）', () => {
    const event = toAgentRunEvent({
      run_id: 'r-1',
      sequence: 1,
      type: 'run_started',
      timestamp: '2026-11-14T10:00:00',
      model: 'm-1',
      mode: 'auto',
      budget: { max_rounds: 60, max_tool_calls: 120 },
      pause_policy: { budget_ratio: 0.8, consecutive_failures: 2 },
    }) as Extract<AgentRunEvent, { type: typeof AGENT_EVENT_TYPE.RUN_STARTED }>

    expect(event.type).toBe(AGENT_EVENT_TYPE.RUN_STARTED)
    expect(event.mode).toBe('auto')
    expect(event.budget).toEqual({
      maxRounds: 60,
      maxToolCalls: 120,
      maxTokens: undefined,
      maxDurationSeconds: undefined,
      maxOutputBytes: undefined,
    })
    expect(event.pausePolicy).toEqual({ budgetRatio: 0.8, consecutiveFailures: 2 })
  })

  it('auto_step：步骤 / 用量 / 上限 / 比例 / 产物 / 续跑提示全部转 camelCase', () => {
    const event = toAgentRunEvent({
      run_id: 'r-1',
      sequence: 7,
      type: 'auto_step',
      timestamp: '2026-11-14T10:00:05',
      mode: 'auto',
      step: 3,
      turn: 4,
      phase: 'resume',
      goal: '全流程跑完',
      plan: '先读标注，再生成用例',
      usage: {
        rounds: 3,
        tool_calls: 5,
        tokens: 1200,
        elapsed_seconds: 61.5,
        output_bytes: 2048,
      },
      limits: { max_rounds: 60, max_tool_calls: 120, max_duration_seconds: 1800 },
      ratios: { max_rounds: 0.05, max_tool_calls: 0.0417, max_duration_seconds: 0.0342 },
      ratio: 0.05,
      consecutive_failures: 1,
      idle_nudges: 0,
      artifact_count: 1,
      artifacts: [{ id: 'a-1', kind: 'report', uri: 's3://r/1' }],
      instruction: '继续推进目标（Auto 第 3 步）',
    }) as Extract<AgentRunEvent, { type: typeof AGENT_EVENT_TYPE.AUTO_STEP }>

    expect(event.progress).toMatchObject({
      step: 3,
      turn: 4,
      phase: 'resume',
      goal: '全流程跑完',
      plan: '先读标注，再生成用例',
      usage: {
        rounds: 3,
        toolCalls: 5,
        tokens: 1200,
        elapsedSeconds: 61.5,
        outputBytes: 2048,
      },
      ratio: 0.05,
      consecutiveFailures: 1,
      artifactCount: 1,
      artifacts: [{ id: 'a-1', kind: 'report', uri: 's3://r/1' }],
      instruction: '继续推进目标（Auto 第 3 步）',
    })
    expect(event.progress.limits?.maxRounds).toBe(60)
    expect(event.progress.ratios?.maxRounds).toBe(0.05)
  })

  it('auto_step：缺 step 视为契约不符，丢弃该事件', () => {
    expect(
      toAgentRunEvent({
        run_id: 'r-1',
        sequence: 8,
        type: 'auto_step',
        timestamp: 't',
      })
    ).toBeNull()
  })

  it('run_paused：暂停原因 / 用量 / 策略阈值', () => {
    const event = toAgentRunEvent({
      run_id: 'r-1',
      sequence: 9,
      type: 'run_paused',
      timestamp: '2026-11-14T10:01:00',
      reason: 'budget_threshold',
      paused: true,
      pause_budget_ratio: 0.8,
      pause_consecutive_failures: 2,
      usage: { rounds: 48, tool_calls: 96, tokens: 400000, elapsed_seconds: 1000, output_bytes: 0 },
      limits: { max_rounds: 60, max_tool_calls: 120, max_tokens: 500000 },
      ratio: 0.8,
      consecutive_failures: 0,
    }) as Extract<AgentRunEvent, { type: typeof AGENT_EVENT_TYPE.RUN_PAUSED }>

    expect(event.pause).toMatchObject({
      reason: AGENT_RUN_PAUSE_REASON.BUDGET_THRESHOLD,
      ratio: 0.8,
      consecutiveFailures: 0,
      policy: { budgetRatio: 0.8, consecutiveFailures: 2 },
    })
    expect(event.pause.usage?.rounds).toBe(48)
    expect(event.pause.at).toBe('2026-11-14T10:01:00Z')
  })

  it('run_resumed：暂停原因与预算确认标记', () => {
    const event = toAgentRunEvent({
      run_id: 'r-1',
      sequence: 10,
      type: 'run_resumed',
      timestamp: 't',
      pause_reason: 'budget_threshold',
      acked_budget_pause: true,
      consecutive_failures: 0,
      budget: { max_rounds: 60 },
    }) as Extract<AgentRunEvent, { type: typeof AGENT_EVENT_TYPE.RUN_RESUMED }>

    expect(event.pauseReason).toBe(AGENT_RUN_PAUSE_REASON.BUDGET_THRESHOLD)
    expect(event.ackedBudgetPause).toBe(true)
    expect(event.budget?.maxRounds).toBe(60)
  })
})

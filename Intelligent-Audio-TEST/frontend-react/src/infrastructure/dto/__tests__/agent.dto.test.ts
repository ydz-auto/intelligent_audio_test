/**
 * Agent DTO 转换单测（INT-2457）：snake_case → camelCase 只在本层发生；
 * 事件载荷兼容「顶层字段」与「payload 内字段」两种后端落法，未知类型丢弃。
 */
import { describe, expect, it } from 'vitest'

import { AGENT_RUN_STATUS } from '@/domain/models/agent'
import {
  toAgentRun,
  toAgentRunCreateDto,
  toAgentRunEvent,
  toAgentSession,
  toAgentSessionCreateDto,
  toAgentSourceRefs,
} from '@/infrastructure/dto/agent.dto'

describe('agent.dto', () => {
  it('会话：session 表字段 snake_case → camelCase', () => {
    const session = toAgentSession({
      id: 's-1',
      title: '对比最近两次报告',
      active_skill: 'report-compare',
      model: 'deepseek-chat',
      created_at: '2026-11-12T03:00:00Z',
      updated_at: '2026-11-12T03:01:00Z',
    })
    expect(session).toEqual({
      id: 's-1',
      title: '对比最近两次报告',
      activeSkill: 'report-compare',
      model: 'deepseek-chat',
      createdAt: '2026-11-12T03:00:00Z',
      updatedAt: '2026-11-12T03:01:00Z',
    })
  })

  it('run：status 归一（未知值按 RUNNING）、token 字段转 camelCase', () => {
    const run = toAgentRun({
      id: 'r-1',
      session_id: 's-1',
      status: 'WAITING_APPROVAL',
      token_in: 120,
      token_out: 340,
      started_at: '2026-11-12T03:02:00Z',
    })
    expect(run.sessionId).toBe('s-1')
    expect(run.status).toBe(AGENT_RUN_STATUS.WAITING_APPROVAL)
    expect(run.tokenIn).toBe(120)
    expect(run.tokenOut).toBe(340)

    expect(toAgentRun({ id: 'r-2', status: 'SOMETHING_NEW' }).status).toBe(
      AGENT_RUN_STATUS.RUNNING
    )
  })

  it('请求体：message / title 透传（空 title 不下发）', () => {
    expect(toAgentRunCreateDto({ message: '你好' })).toEqual({ message: '你好' })
    expect(toAgentSessionCreateDto('会话标题')).toEqual({ title: '会话标题' })
    expect(toAgentSessionCreateDto()).toEqual({})
  })

  it('sourceRefs：report_id/metric_id/data_version → camelCase，缺 report_id 丢弃', () => {
    expect(
      toAgentSourceRefs([
        { report_id: 12, metric_id: 'pass_rate', data_version: 'v3', verified: true },
        { metric_id: 'x' },
      ])
    ).toEqual([
      { reportId: 12, metricId: 'pass_rate', dataVersion: 'v3', verified: true },
    ])
    expect(toAgentSourceRefs([])).toBeUndefined()
    expect(toAgentSourceRefs(undefined)).toBeUndefined()
  })

  it('事件：顶层字段形态（run_id/sequence/type/payload）', () => {
    const event = toAgentRunEvent({
      run_id: 'r-1',
      sequence: 7,
      type: 'message_delta',
      timestamp: '2026-11-12T03:03:00Z',
      payload: { message_id: 'm-9', delta: '你好' },
    })
    expect(event).toEqual({
      runId: 'r-1',
      sequence: 7,
      type: 'message_delta',
      timestamp: '2026-11-12T03:03:00Z',
      messageId: 'm-9',
      delta: '你好',
    })
  })

  it('事件：payload 内嵌字段形态（后端把 run_id/type 也放 payload）', () => {
    const event = toAgentRunEvent({
      payload: {
        run_id: 'r-2',
        sequence: 3,
        type: 'tool_call',
        tool_call_id: 'tc-1',
        tool: 'report_query',
        risk: 'READ',
        summary: '查询报告 12 的指标',
      },
    })
    expect(event).toMatchObject({
      runId: 'r-2',
      sequence: 3,
      type: 'tool_call',
      toolCallId: 'tc-1',
      tool: 'report_query',
      risk: 'READ',
      summary: '查询报告 12 的指标',
    })
  })

  it('事件：tool_result 带 sourceRefs；run_finished 未知状态回退成功', () => {
    const toolResult = toAgentRunEvent({
      run_id: 'r-3',
      sequence: 4,
      type: 'tool_result',
      payload: {
        tool_call_id: 'tc-1',
        status: 'FAILED',
        summary: '超时',
        source_refs: [{ report_id: 5 }],
      },
    })
    expect(toolResult).toMatchObject({
      type: 'tool_result',
      status: 'FAILED',
      summary: '超时',
      sourceRefs: [{ reportId: 5 }],
    })

    const finished = toAgentRunEvent({
      run_id: 'r-3',
      sequence: 5,
      type: 'run_finished',
      payload: { status: 'UNKNOWN_STATUS' },
    })
    expect(finished).toMatchObject({
      type: 'run_finished',
      status: AGENT_RUN_STATUS.SUCCEEDED,
    })
  })

  it('事件：未知类型 / 缺 sequence → 丢弃（不把未知载荷当已知结构渲染）', () => {
    expect(
      toAgentRunEvent({ run_id: 'r', sequence: 1, type: 'brand_new_event' })
    ).toBeNull()
    expect(toAgentRunEvent({ run_id: 'r', type: 'message_delta' })).toBeNull()
    expect(
      toAgentRunEvent({ run_id: 'r', sequence: 1, type: 'message_delta', payload: {} })
    ).toBeNull()
  })
})

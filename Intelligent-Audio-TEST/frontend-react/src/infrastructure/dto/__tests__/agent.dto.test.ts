/**
 * Agent DTO 转换单测（INT-2457 / INT-2519）：snake_case → camelCase 只在本层发生；
 * 只认 agent_service 真实形态（平铺 snake_case 帧 / {run,created} / {items}），
 * 旧草案形态（嵌套 payload / camelCase 键 / 扁平 run / 裸数组）必须判契约错误。
 */
import { describe, expect, it } from 'vitest'

import { AGENT_RUN_STATUS } from '@/domain/models/agent'
import {
  AgentContractError,
  toAgentApproval,
  toAgentApprovalDecisionDto,
  toAgentApprovalDecisionResult,
  toAgentApprovalObjectRef,
  toAgentApprovals,
  toAgentRun,
  toAgentRunCreateDto,
  toAgentRunEvent,
  toAgentRunFromCreateResponse,
  toAgentSession,
  toAgentSessionCreateDto,
  toAgentSessionDetail,
  toAgentSourceRefs,
  toUtcIso,
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

  it('事件：真实平铺帧（事件字段与 run_id/sequence/type 同层，无 payload）', () => {
    const event = toAgentRunEvent({
      run_id: 'r-1',
      sequence: 7,
      type: 'message_delta',
      timestamp: '2026-11-12T03:03:00Z',
      message_id: 'm-9',
      delta: '你好',
      index: 0,
      turn: 1,
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

  it('事件：嵌套 payload 形态不再兼容（真实帧字段平铺，嵌套即丢弃）', () => {
    const event = toAgentRunEvent({
      payload: {
        run_id: 'r-2',
        sequence: 3,
        type: 'tool_call',
        tool_call_id: 'tc-1',
        tool: 'report_query',
      },
    })
    expect(event).toBeNull()
  })

  it('事件：camelCase 键不再兜底（真实帧只有 snake_case）', () => {
    expect(
      toAgentRunEvent({
        run_id: 'r-1',
        sequence: 1,
        type: 'message_delta',
        messageId: 'm-1',
        delta: '你好',
      })
    ).toBeNull()
    expect(
      toAgentRunEvent({
        run_id: 'r-1',
        sequence: 2,
        type: 'tool_call',
        toolCallId: 'tc-1',
        name: 'report_query',
      })
    ).toBeNull()
  })

  it('事件：tool_call 摘要只取 arguments（真实帧无 summary/args_summary）', () => {
    const event = toAgentRunEvent({
      run_id: 'r-3',
      sequence: 6,
      type: 'tool_call',
      tool_call_id: 'tc-2',
      tool: 'report_query',
      risk: 'READ',
      arguments: { report_id: 12 },
      // 旧草案键：不再读取，避免掩盖真实契约漂移
      summary: '旧草案摘要',
      args_summary: '旧草案摘要',
      turn: 1,
    })
    expect(event).toMatchObject({
      type: 'tool_call',
      summary: '{"report_id":12}',
    })
  })

  it('事件：tool_result 真实载荷 {ok, content, error_code} → FAILED + 摘要 + 错误码', () => {
    const failed = toAgentRunEvent({
      run_id: 'r-3',
      sequence: 4,
      type: 'tool_result',
      tool_call_id: 'tc-1',
      tool: 'query',
      ok: false,
      content: 'boom',
      error_code: 'E1',
      // 旧草案键：不再读取，摘要只取真实的 content
      summary: '旧草案摘要',
      result_summary: '旧草案摘要',
      turn: 1,
    })
    expect(failed).toMatchObject({
      type: 'tool_result',
      status: 'FAILED',
      summary: 'boom',
      errorCode: 'E1',
    })

    const succeeded = toAgentRunEvent({
      run_id: 'r-3',
      sequence: 5,
      type: 'tool_result',
      tool_call_id: 'tc-1',
      ok: true,
      content: '返回 8 项指标',
    })
    expect(succeeded).toMatchObject({
      type: 'tool_result',
      status: 'SUCCEEDED',
      summary: '返回 8 项指标',
    })

    // sourceRefs 仅在载荷带 source_refs 时映射（M0 后端不产出，不伪造）
    const withRefs = toAgentRunEvent({
      run_id: 'r-3',
      sequence: 6,
      type: 'tool_result',
      tool_call_id: 'tc-1',
      ok: true,
      source_refs: [{ report_id: 5 }],
    })
    expect(withRefs).toMatchObject({ sourceRefs: [{ reportId: 5 }] })
  })

  it('事件：run_finished 保留真实状态；异常状态有 error 判失败', () => {
    const cancelled = toAgentRunEvent({
      run_id: 'r-3',
      sequence: 5,
      type: 'run_finished',
      status: 'CANCELLED',
      reason: 'user_cancelled',
      error: null,
    })
    expect(cancelled).toMatchObject({
      type: 'run_finished',
      status: AGENT_RUN_STATUS.CANCELLED,
    })

    const failed = toAgentRunEvent({
      run_id: 'r-3',
      sequence: 5,
      type: 'run_finished',
      status: 'UNKNOWN_STATUS',
      error: '工具连续失败',
    })
    expect(failed).toMatchObject({ type: 'run_finished', status: AGENT_RUN_STATUS.FAILED })

    const fallback = toAgentRunEvent({
      run_id: 'r-3',
      sequence: 5,
      type: 'run_finished',
      status: 'UNKNOWN_STATUS',
    })
    expect(fallback).toMatchObject({
      type: 'run_finished',
      status: AGENT_RUN_STATUS.SUCCEEDED,
    })
  })

  it('事件：error 帧按 code 标记可恢复（网关上游中断）与终态错误', () => {
    // 网关 _sse_error_frame 合成帧：字段平铺，code=UPSTREAM_*
    const interrupted = toAgentRunEvent({
      run_id: 'r-4',
      sequence: 9,
      type: 'error',
      timestamp: 't',
      code: 'UPSTREAM_UNAVAILABLE',
      message: '上游事件流转发中断，请按 Last-Event-ID 续传',
    })
    expect(interrupted).toMatchObject({
      type: 'error',
      sequence: 9,
      errorCode: 'UPSTREAM_UNAVAILABLE',
      recoverable: true,
    })

    const upstreamError = toAgentRunEvent({
      run_id: 'r-4',
      sequence: 9,
      type: 'error',
      code: 'UPSTREAM_ERROR',
      message: '上游事件流返回 500',
    })
    expect(upstreamError).toMatchObject({ recoverable: true })

    // agent_service 的业务错误（如重启写操作待确认）仍是终态错误
    const terminal = toAgentRunEvent({
      run_id: 'r-4',
      sequence: 10,
      type: 'error',
      code: 'RESTART_WRITE_UNVERIFIED',
      message: '进程重启前的中断写操作需人工确认',
    })
    expect(terminal).toMatchObject({
      type: 'error',
      errorCode: 'RESTART_WRITE_UNVERIFIED',
      recoverable: false,
    })
  })

  it('响应信封：run 创建 {run, created} / 会话 {session,messages,runs} / approvals {items}', () => {
    const run = toAgentRunFromCreateResponse({
      run: { id: 'r-1', session_id: 's-1', status: 'QUEUED' },
      created: true,
    })
    expect(run).toMatchObject({ id: 'r-1', sessionId: 's-1', status: AGENT_RUN_STATUS.QUEUED })
    // 扁平 run（旧草案 / 单测桩）不再是合法形态
    expect(() =>
      toAgentRunFromCreateResponse({
        id: 'r-2',
        status: 'RUNNING',
      } as unknown as Parameters<typeof toAgentRunFromCreateResponse>[0])
    ).toThrow(AgentContractError)

    const detail = toAgentSessionDetail({
      session: { id: 's-1', title: '会话' },
      messages: [{ role: 'user', content: '你好' }],
      runs: [{ id: 'r-1', session_id: 's-1', status: 'SUCCEEDED' }],
    })
    expect(detail.session.id).toBe('s-1')
    expect(detail.messages).toEqual([{ role: 'user', content: '你好', toolCallId: undefined }])
    expect(detail.runs[0].id).toBe('r-1')

    expect(toAgentApprovals({ items: [] })).toEqual([])
    expect(toAgentApprovals({ items: [{ id: 'a-1', run_id: 'r-1', status: 'PENDING' }] })).toMatchObject([
      { id: 'a-1', status: 'PENDING' },
    ])
    // 裸数组（旧草案）不再是合法形态
    expect(() =>
      toAgentApprovals([
        { id: 'a-1', run_id: 'r-1', status: 'PENDING' },
      ] as unknown as Parameters<typeof toAgentApprovals>[0])
    ).toThrow(AgentContractError)
    expect(() =>
      toAgentApprovals({} as Parameters<typeof toAgentApprovals>[0])
    ).toThrow(AgentContractError)
  })

  it('事件：error 帧读真实键 {code, message}', () => {
    expect(
      toAgentRunEvent({
        run_id: 'r-1',
        sequence: 8,
        type: 'error',
        code: 'LLM_TIMEOUT',
        message: '模型超时',
        // 旧草案键：不再读取
        error_code: 'OLD',
        detail: '旧草案详情',
      })
    ).toMatchObject({
      type: 'error',
      errorCode: 'LLM_TIMEOUT',
      errorMessage: '模型超时',
    })
  })

  it('事件：未知类型 / 缺 sequence / 缺必需键 → 丢弃（不把未知载荷当已知结构渲染）', () => {
    expect(
      toAgentRunEvent({ run_id: 'r', sequence: 1, type: 'brand_new_event' })
    ).toBeNull()
    expect(toAgentRunEvent({ run_id: 'r', type: 'message_delta' })).toBeNull()
    expect(
      toAgentRunEvent({ run_id: 'r', sequence: 1, type: 'message_delta' })
    ).toBeNull()
    expect(
      toAgentRunEvent({ run_id: 'r', sequence: 1, type: 'message_delta', payload: { message_id: 'm-1', delta: '你好' } })
    ).toBeNull()
  })
})

describe('agent.dto 审批与时间线（INT-2472）', () => {
  it('审批单：proposal / diff / 决策人时间 snake_case → camelCase', () => {
    const approval = toAgentApproval({
      id: 'ap-1',
      run_id: 'r-1',
      tool_call_id: 'tc-1',
      status: 'APPROVED',
      proposal: {
        tool: 'memory_write',
        risk: 'WRITE',
        arguments: { section: 'USER_PROFILE' },
        args_hash: 'abc',
        idempotency_key: 'k-1',
        step_id: 'step-1',
        turn: 2,
        requested_by: 9,
        session_id: 's-1',
      },
      diff: { kind: 'rest_request', method: 'POST', path: '/api/v1/memory' },
      expires_at: '2026-11-14T02:15:00Z',
      decided_by: 7,
      decided_at: '2026-11-14T02:03:00Z',
      created_at: '2026-11-14T02:00:00Z',
    })
    expect(approval).toMatchObject({
      id: 'ap-1',
      runId: 'r-1',
      toolCallId: 'tc-1',
      status: 'APPROVED',
      expiresAt: '2026-11-14T02:15:00Z',
      decidedBy: 7,
      decidedAt: '2026-11-14T02:03:00Z',
      createdAt: '2026-11-14T02:00:00Z',
    })
    expect(approval.proposal).toMatchObject({
      tool: 'memory_write',
      risk: 'WRITE',
      arguments: { section: 'USER_PROFILE' },
      argsHash: 'abc',
      idempotencyKey: 'k-1',
      stepId: 'step-1',
      turn: 2,
      requestedBy: 9,
      sessionId: 's-1',
    })
    expect(approval.diff).toEqual({
      kind: 'rest_request',
      method: 'POST',
      path: '/api/v1/memory',
    })
  })

  it('审批单：risk 缺失 / 未知时不降级成 READ（安全：未知风险不能伪装只读）', () => {
    expect(
      toAgentApproval({ id: 'ap-1', proposal: { tool: 'x' } }).proposal?.risk
    ).toBeUndefined()
    expect(
      toAgentApproval({
        id: 'ap-1',
        proposal: { tool: 'x', risk: 'SOMETHING_NEW' },
      }).proposal?.risk
    ).toBeUndefined()
  })

  it('审批决策响应：{approval, run_status} → 领域结果；缺信封判契约错误', () => {
    const result = toAgentApprovalDecisionResult({
      approval: {
        id: 'ap-1',
        run_id: 'r-1',
        status: 'APPROVED',
        proposal: { tool: 'memory_write', risk: 'WRITE' },
      },
      run_status: 'WAITING_APPROVAL',
    })
    expect(result.approval.status).toBe('APPROVED')
    expect(result.runStatus).toBe(AGENT_RUN_STATUS.WAITING_APPROVAL)

    expect(() =>
      toAgentApprovalDecisionResult({} as never)
    ).toThrow(AgentContractError)
  })

  it('审批决策请求：只有二次确认才带 confirm（INT-2467）', () => {
    expect(toAgentApprovalDecisionDto('APPROVE')).toEqual({
      decision: 'APPROVE',
    })
    expect(toAgentApprovalDecisionDto('REJECT', true)).toEqual({
      decision: 'REJECT',
      confirm: true,
    })
    expect(toAgentApprovalDecisionDto('APPROVE', true)).toEqual({
      decision: 'APPROVE',
      confirm: true,
    })
  })

  it('run / run_started：budget 上限转 camelCase（时间线展示预算消耗）', () => {
    const run = toAgentRun({
      id: 'r-1',
      status: 'RUNNING',
      budget: {
        max_rounds: 12,
        max_tool_calls: 40,
        max_tokens: 128000,
        max_duration_seconds: 600,
        max_output_bytes: 262144,
      },
      token_in: 10,
      token_out: 20,
    })
    expect(run.budget).toEqual({
      maxRounds: 12,
      maxToolCalls: 40,
      maxTokens: 128000,
      maxDurationSeconds: 600,
      maxOutputBytes: 262144,
    })
    expect(run.tokenIn).toBe(10)
    expect(run.tokenOut).toBe(20)

    const event = toAgentRunEvent({
      run_id: 'r-1',
      sequence: 1,
      type: 'run_started',
      model: 'deepseek-chat',
      budget: { max_rounds: 12, max_tool_calls: 40 },
    })
    expect(event).toMatchObject({
      type: 'run_started',
      budget: { maxRounds: 12, maxToolCalls: 40 },
    })
  })

  it('approval_required 事件：approval_id / tool / risk / expires_at / proposal', () => {
    const event = toAgentRunEvent({
      run_id: 'r-1',
      sequence: 2,
      type: 'approval_required',
      approval_id: 'ap-1',
      tool_call_id: 'tc-1',
      tool: 'memory_write',
      risk: 'DESTRUCTIVE',
      expires_at: '2026-11-14T02:15:00Z',
      proposal: {
        tool: 'memory_write',
        risk: 'DESTRUCTIVE',
        step_id: 'step-1',
        turn: 3,
      },
    })
    expect(event).toMatchObject({
      type: 'approval_required',
      approvalId: 'ap-1',
      toolCallId: 'tc-1',
      tool: 'memory_write',
      risk: 'DESTRUCTIVE',
      expiresAt: '2026-11-14T02:15:00Z',
      proposal: { tool: 'memory_write', risk: 'DESTRUCTIVE', stepId: 'step-1', turn: 3 },
    })
  })

  it('context_compacted 事件：层级 / token / 裁剪数 / 调试开关', () => {
    const event = toAgentRunEvent({
      run_id: 'r-1',
      sequence: 3,
      type: 'context_compacted',
      level: 'L2_DEDUPE',
      snapshot_version: 2,
      token_count_before: 1200,
      token_count_after: 800,
      dropped_count: 4,
      debug: true,
    })
    expect(event).toMatchObject({
      type: 'context_compacted',
      level: 'L2_DEDUPE',
      snapshotVersion: 2,
      tokenCountBefore: 1200,
      tokenCountAfter: 800,
      droppedCount: 4,
      debug: true,
    })
  })
})

describe('agent.dto 时间戳口径（INT-2472）', () => {
  it('后端 naive UTC 时间戳补 Z：否则 UTC+8 下审批单会被判早 8 小时过期', () => {
    expect(toUtcIso('2026-11-13T18:49:24.031859')).toBe(
      '2026-11-13T18:49:24.031859Z'
    )
    // 已带时区 / 非 ISO 原样返回
    expect(toUtcIso('2026-11-13T18:49:24Z')).toBe('2026-11-13T18:49:24Z')
    expect(toUtcIso('not-a-date')).toBe('not-a-date')
    expect(toUtcIso(undefined)).toBeUndefined()

    const approval = toAgentApproval({
      id: 'ap-1',
      expires_at: '2026-11-13T18:49:24.031859',
      decided_at: '2026-11-13T18:50:24.031859',
      created_at: '2026-11-13T18:34:24.031859',
    })
    expect(approval.expiresAt).toBe('2026-11-13T18:49:24.031859Z')
    expect(approval.decidedAt).toBe('2026-11-13T18:50:24.031859Z')
    expect(approval.createdAt).toBe('2026-11-13T18:34:24.031859Z')

    const event = toAgentRunEvent({
      run_id: 'r-1',
      sequence: 3,
      type: 'approval_required',
      approval_id: 'ap-1',
      expires_at: '2026-11-13T18:49:24.031859',
      timestamp: '2026-11-13T18:34:24.031859',
    })
    expect(event).toMatchObject({
      expiresAt: '2026-11-13T18:49:24.031859Z',
      timestamp: '2026-11-13T18:34:24.031859Z',
    })
  })
})

describe('agent.dto 审批拆单批次（INT-2573 §9.4.1）', () => {
  it('批次字段 snake_case → camelCase：batch_id / batch_index / batch_total / object_ref / proposal.object_count', () => {
    const approval = toAgentApproval({
      id: 'ap-2',
      run_id: 'r-1',
      tool_call_id: 'tc-1',
      status: 'PENDING',
      proposal: {
        tool: 'tag_group_manage',
        risk: 'WRITE',
        arguments: { ids: ['c-2'] },
        object_count: 21,
      },
      batch_id: 'batch-1',
      batch_index: 2,
      batch_total: 21,
      object_ref: { kind: 'testcase', ids: ['c-2'] },
    })
    expect(approval).toMatchObject({
      batchId: 'batch-1',
      batchIndex: 2,
      batchTotal: 21,
      objectRef: { kind: 'testcase', ids: ['c-2'] },
    })
    expect(approval.proposal?.objectCount).toBe(21)
    // 领域层不出现 snake_case（架构红线）
    expect(JSON.stringify(approval)).not.toContain('batch_id')
    expect(JSON.stringify(approval)).not.toContain('object_ref')
  })

  it('旧单 / 缺批次字段：按单张兼容（batchId 空、序号与总数都是 1）', () => {
    const approval = toAgentApproval({ id: 'ap-old', run_id: 'r-1', status: 'PENDING' })
    expect(approval.batchId).toBeUndefined()
    expect(approval.batchIndex).toBe(1)
    expect(approval.batchTotal).toBe(1)
    expect(approval.objectRef).toBeUndefined()
    // 后端显式下发 batch_id=null 也按单张处理
    expect(
      toAgentApproval({ id: 'ap-old', batch_id: null, batch_total: 1 })
    ).toMatchObject({ batchId: undefined, batchIndex: 1, batchTotal: 1 })
  })

  it('批次序号 / 总数的非法值归一为 1（0 / 负数 / 小数 / 字符串）', () => {
    expect(
      toAgentApproval({ id: 'ap-1', batch_index: 0, batch_total: 0 })
    ).toMatchObject({ batchIndex: 1, batchTotal: 1 })
    expect(
      toAgentApproval({
        id: 'ap-1',
        batch_index: 1.5,
        batch_total: '21' as unknown as number,
      })
    ).toMatchObject({ batchIndex: 1, batchTotal: 1 })
    expect(
      toAgentApproval({ id: 'ap-1', batch_index: -3, batch_total: 21 })
    ).toMatchObject({ batchIndex: 1, batchTotal: 21 })
  })

  it('object_ref：数字 id 字符串化；非枚举范围 ids 空保留 kind；空对象不伪造摘要', () => {
    expect(
      toAgentApprovalObjectRef({ kind: 'audio', ids: [1, 2, 'a-3'] })
    ).toEqual({ kind: 'audio', ids: ['1', '2', 'a-3'] })
    // mode=all 这类非枚举范围：ids 为空但 kind 仍在（展示「按范围执行」）
    expect(toAgentApprovalObjectRef({ kind: 'testcase', ids: [] })).toEqual({
      kind: 'testcase',
      ids: [],
    })
    expect(toAgentApprovalObjectRef({ kind: '', ids: [] })).toBeUndefined()
    expect(toAgentApprovalObjectRef({})).toBeUndefined()
    expect(toAgentApprovalObjectRef(null)).toBeUndefined()
    expect(toAgentApprovalObjectRef('testcase')).toBeUndefined()
  })

  it('审批列表：每张单各自带批次字段（同批 batch_id 相同、batch_index 1..N）', () => {
    const items = toAgentApprovals({
      items: [
        {
          id: 'ap-1',
          status: 'PENDING',
          batch_id: 'batch-1',
          batch_index: 1,
          batch_total: 2,
          object_ref: { kind: 'testcase', ids: ['c-1'] },
        },
        {
          id: 'ap-2',
          status: 'PENDING',
          batch_id: 'batch-1',
          batch_index: 2,
          batch_total: 2,
          object_ref: { kind: 'testcase', ids: ['c-2'] },
        },
      ],
    })
    expect(items.map((item) => item.batchId)).toEqual(['batch-1', 'batch-1'])
    expect(items.map((item) => item.batchIndex)).toEqual([1, 2])
    expect(items.map((item) => item.batchTotal)).toEqual([2, 2])
  })

  it('approval_required 事件：拆单载荷带 batch_id / batch_index / batch_total', () => {
    const event = toAgentRunEvent({
      run_id: 'r-1',
      sequence: 2,
      type: 'approval_required',
      approval_id: 'ap-2',
      tool_call_id: 'tc-1',
      tool: 'tag_group_manage',
      risk: 'WRITE',
      proposal: { tool: 'tag_group_manage', object_count: 21 },
      batch_id: 'batch-1',
      batch_index: 2,
      batch_total: 21,
    })
    expect(event).toMatchObject({
      type: 'approval_required',
      approvalId: 'ap-2',
      batchId: 'batch-1',
      batchIndex: 2,
      batchTotal: 21,
      proposal: { objectCount: 21 },
    })

    // 未拆单事件：字段缺省，按单张渲染
    const single = toAgentRunEvent({
      run_id: 'r-1',
      sequence: 3,
      type: 'approval_required',
      approval_id: 'ap-3',
    })
    expect(single).toMatchObject({
      batchId: undefined,
      batchIndex: undefined,
      batchTotal: undefined,
    })
  })
})

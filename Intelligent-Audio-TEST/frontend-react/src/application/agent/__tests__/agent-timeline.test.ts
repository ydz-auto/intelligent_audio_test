/**
 * Run 时间线归约单测（INT-2472 §12.2 / 拍板增补 3）：
 * - 事件顺序与后端 sequence 一致，message_delta 连续聚合（首条 sequence + 最新 lastSequence）；
 * - tool_call / tool_result / approval_required / context_compacted / run_finished 各成一目；
 * - 审批决策（决策人 / 时间）回填审批条目，不改变事件顺序；
 * - context_compacted 的调试标记只在后端 debug 开启时出现。
 */
import { describe, expect, it } from 'vitest'

import {
  AGENT_APPROVAL_STATUS,
  AGENT_EVENT_TYPE,
  AGENT_RUN_STATUS,
  AGENT_TOOL_RISK,
  AGENT_TOOL_RESULT_STATUS,
  type AgentRunEvent,
} from '@/domain/models/agent'
import {
  AGENT_TIMELINE_KIND,
  appendTimelineEntry,
  applyApprovalToTimeline,
  countTimelineToolCalls,
  formatClock,
  type AgentTimelineEntry,
} from '@/application/agent/agent-timeline'

function reduce(events: AgentRunEvent[]): AgentTimelineEntry[] {
  return events.reduce<AgentTimelineEntry[]>(
    (entries, event) => appendTimelineEntry(entries, event),
    []
  )
}

const base = { runId: 'r-1', timestamp: '2026-11-14T02:00:00Z' }

describe('agent-timeline', () => {
  it('按 sequence 归约完整事件链，message_delta 连续聚合', () => {
    const entries = reduce([
      {
        ...base,
        type: AGENT_EVENT_TYPE.RUN_STARTED,
        sequence: 1,
        status: AGENT_RUN_STATUS.RUNNING,
        model: 'deepseek-chat',
      },
      {
        ...base,
        type: AGENT_EVENT_TYPE.MESSAGE_DELTA,
        sequence: 2,
        messageId: 'm-1',
        delta: '你好',
      },
      {
        ...base,
        type: AGENT_EVENT_TYPE.MESSAGE_DELTA,
        sequence: 3,
        messageId: 'm-1',
        delta: '，世界',
      },
      {
        ...base,
        type: AGENT_EVENT_TYPE.TOOL_CALL,
        sequence: 4,
        toolCallId: 'tc-1',
        tool: 'report_get_facts',
        risk: AGENT_TOOL_RISK.READ,
      },
      {
        ...base,
        type: AGENT_EVENT_TYPE.TOOL_RESULT,
        sequence: 5,
        toolCallId: 'tc-1',
        status: AGENT_TOOL_RESULT_STATUS.SUCCEEDED,
        summary: '获取 3 条事实',
      },
      {
        ...base,
        type: AGENT_EVENT_TYPE.RUN_FINISHED,
        sequence: 6,
        status: AGENT_RUN_STATUS.SUCCEEDED,
      },
    ])

    expect(entries.map((entry) => entry.kind)).toEqual([
      AGENT_TIMELINE_KIND.RUN_STARTED,
      AGENT_TIMELINE_KIND.MESSAGE,
      AGENT_TIMELINE_KIND.TOOL_CALL,
      AGENT_TIMELINE_KIND.TOOL_RESULT,
      AGENT_TIMELINE_KIND.RUN_FINISHED,
    ])
    // sequence 严格递增（message 聚合条保留首条序号）
    expect(entries.map((entry) => entry.sequence)).toEqual([1, 2, 4, 5, 6])
    const message = entries[1]
    expect(message.lastSequence).toBe(3)
    expect(message.charCount).toBe('你好，世界'.length)
    expect(message.detail).toBe(`${'你好，世界'.length} 字`)
    expect(countTimelineToolCalls(entries)).toBe(1)
    // 终态由徽标展示，detail 不再重复「运行结束 · 已完成」（P3-6）
    const finished = entries[entries.length - 1]
    expect(finished.detail).toBeUndefined()
    expect(finished.status).toBe(AGENT_RUN_STATUS.SUCCEEDED)
  })

  it('中间插入其他事件后 message_delta 另起一条（不跨事件聚合）', () => {
    const entries = reduce([
      {
        ...base,
        type: AGENT_EVENT_TYPE.MESSAGE_DELTA,
        sequence: 1,
        messageId: 'm-1',
        delta: '第一段',
      },
      {
        ...base,
        type: AGENT_EVENT_TYPE.TOOL_CALL,
        sequence: 2,
        toolCallId: 'tc-1',
        tool: 'report_query_metrics',
        risk: AGENT_TOOL_RISK.READ,
      },
      {
        ...base,
        type: AGENT_EVENT_TYPE.MESSAGE_DELTA,
        sequence: 3,
        messageId: 'm-1',
        delta: '第二段',
      },
    ])
    expect(entries).toHaveLength(3)
    expect(entries[0].lastSequence).toBe(1)
    expect(entries[2].sequence).toBe(3)
  })

  it('approval_required 带风险 / 过期时间，决策后回填决策人与时间', () => {
    let entries = reduce([
      {
        ...base,
        type: AGENT_EVENT_TYPE.APPROVAL_REQUIRED,
        sequence: 7,
        approvalId: 'ap-1',
        toolCallId: 'tc-9',
        tool: 'memory_write',
        risk: AGENT_TOOL_RISK.WRITE,
        expiresAt: '2026-11-14T02:15:00Z',
      },
    ])
    const approval = entries[0]
    expect(approval.kind).toBe(AGENT_TIMELINE_KIND.APPROVAL)
    expect(approval.risk).toBe(AGENT_TOOL_RISK.WRITE)
    expect(approval.status).toBe(AGENT_APPROVAL_STATUS.PENDING)
    expect(approval.detail).toContain('写操作')
    expect(approval.detail).toContain('有效期至')

    entries = applyApprovalToTimeline(entries, {
      id: 'ap-1',
      runId: 'r-1',
      toolCallId: 'tc-9',
      status: AGENT_APPROVAL_STATUS.APPROVED,
      proposal: { tool: 'memory_write', risk: AGENT_TOOL_RISK.WRITE },
      decidedBy: 7,
      decidedAt: '2026-11-14T02:03:00Z',
    })
    expect(entries[0].status).toBe(AGENT_APPROVAL_STATUS.APPROVED)
    expect(entries[0].decidedBy).toBe(7)
    expect(entries[0].detail).toContain('已批准')
    // 决策人数字 id 不在时间线文案里直出（P3-4：由界面层解析成「我 / 其他用户」）
    expect(entries[0].detail).not.toContain('决策人 7')
    expect(entries[0].detail).toContain('决策于')
    // 决策不产生事件，序号不变
    expect(entries[0].sequence).toBe(7)
  })

  it('context_compacted 带层级 / token / 裁剪数与调试标记', () => {
    const entries = reduce([
      {
        ...base,
        type: AGENT_EVENT_TYPE.CONTEXT_COMPACTED,
        sequence: 11,
        level: 'L2_DEDUPE',
        tokenCountBefore: 1200,
        tokenCountAfter: 800,
        droppedCount: 4,
        debug: true,
      },
    ])
    expect(entries[0].kind).toBe(AGENT_TIMELINE_KIND.CONTEXT_COMPACTED)
    expect(entries[0].debug).toBe(true)
    expect(entries[0].detail).toBe('层级 L2_DEDUPE · token 1200 → 800 · 裁剪 4 条')
  })

  it('可恢复的上游中断帧保留在时间线（不丢事件）', () => {
    const entries = reduce([
      {
        ...base,
        type: AGENT_EVENT_TYPE.ERROR,
        sequence: 5,
        errorCode: 'UPSTREAM_ERROR',
        errorMessage: '上游中断',
        recoverable: true,
      },
    ])
    expect(entries[0].kind).toBe(AGENT_TIMELINE_KIND.ERROR)
    expect(entries[0].label).toBe('上游中断（可续传）')
    expect(entries[0].detail).toContain('UPSTREAM_ERROR')
  })

  it('formatClock：无效时间原样返回，有效时间不抛错', () => {
    expect(formatClock('not-a-date')).toBe('not-a-date')
    expect(formatClock(undefined)).toBe('')
    expect(formatClock('2026-11-14T02:00:00Z')).not.toBe('')
  })
})

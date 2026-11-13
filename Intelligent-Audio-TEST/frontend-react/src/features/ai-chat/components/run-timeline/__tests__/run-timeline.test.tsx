/**
 * Run 时间线组件单测（INT-2472 §12.2 / 拍板增补 3）：
 * 展开后按后端 sequence 顺序渲染事件（sequence 落在 data 属性上便于核对）、
 * 审批决策人与时间、context_compacted 调试标记、预算上限与 token 消耗。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { AGENT_APPROVAL_STATUS, AGENT_RUN_STATUS } from '@/domain/models/agent'
import type { AgentTimelineEntry } from '@/application/agent/agent-timeline'
import { RunTimeline } from '@/features/ai-chat/components/run-timeline/run-timeline'

const entries: AgentTimelineEntry[] = [
  {
    kind: 'run_started',
    sequence: 1,
    lastSequence: 1,
    at: '2026-11-14T02:00:00Z',
    label: '运行开始',
    detail: '模型 deepseek-chat',
  },
  {
    kind: 'tool_call',
    sequence: 2,
    lastSequence: 2,
    at: '2026-11-14T02:00:01Z',
    label: '调用 记住偏好',
    toolCallId: 'tc-1',
  },
  {
    kind: 'approval',
    sequence: 3,
    lastSequence: 3,
    at: '2026-11-14T02:00:02Z',
    label: '等待审批：记住偏好',
    status: AGENT_APPROVAL_STATUS.APPROVED,
    approvalId: 'ap-1',
    decidedBy: 7,
    decidedAt: '2026-11-14T02:00:30Z',
    detail: '写操作 · 已批准 · 决策人 7',
  },
  {
    kind: 'context_compacted',
    sequence: 4,
    lastSequence: 4,
    at: '2026-11-14T02:00:03Z',
    label: '上下文压缩',
    detail: '层级 L2_DEDUPE · token 1200 → 800 · 裁剪 4 条',
    debug: true,
  },
  {
    kind: 'run_finished',
    sequence: 5,
    lastSequence: 5,
    at: '2026-11-14T02:00:04Z',
    label: '运行结束',
    status: AGENT_RUN_STATUS.SUCCEEDED,
    detail: '已完成',
  },
]

describe('RunTimeline', () => {
  it('默认折叠；展开后按 sequence 顺序渲染事件与审批决策信息', async () => {
    const { container } = render(
      <RunTimeline
        entries={entries}
        run={{
          id: 'r-1',
          sessionId: 's-1',
          status: AGENT_RUN_STATUS.SUCCEEDED,
          tokenIn: 120,
          tokenOut: 30,
          budget: { maxTokens: 1000, maxToolCalls: 40 },
        }}
      />
    )
    expect(container.querySelector('[data-agent-run-timeline]')).not.toBeNull()
    // 默认折叠：事件内容不可见（DOM 是否渲染由 Base UI Collapsible 决定，按可见性断言）
    const folded = screen.queryByText('运行结束')
    if (folded) expect(folded).not.toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: /运行时间线/ }))

    const rendered = Array.from(
      container.querySelectorAll('[data-timeline-sequence]')
    )
    expect(rendered.map((node) => node.getAttribute('data-timeline-sequence'))).toEqual([
      '1',
      '2',
      '3',
      '4',
      '5',
    ])
    expect(screen.getByText(/决策人 7/)).toBeVisible()
    expect(
      container.querySelector('[data-timeline-debug="true"]')
    ).not.toBeNull()
    expect(screen.getByText('token 150（入 120 / 出 30）')).toBeVisible()
    const budget = container.querySelector('[data-timeline-budget]')?.textContent ?? ''
    expect(budget).toContain('工具 ≤ 40')
    expect(budget).toContain('token ≤ 1000')
  })

  it('无事件时不渲染（时间线空态不占位）', () => {
    const { container } = render(<RunTimeline entries={[]} />)
    expect(container.firstChild).toBeNull()
  })
})

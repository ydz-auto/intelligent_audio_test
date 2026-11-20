/**
 * 审批面板单测（INT-2472 §9.4 审批粒度）：
 * - 同一步骤（step_id）的写操作归到一组、一次看全（计划级批量展示）；
 * - 决策仍逐条（卡片各自按钮，没有批量批准）；
 * - 已决 / 过期单收进「已处理」折叠区，重连后不重复弹出可操作卡；
 * - 加载 / 空 / 错误态齐全，计数与工具卡同源。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import {
  AGENT_APPROVAL_COPY,
  AGENT_APPROVAL_STATUS,
  AGENT_TOOL_RISK,
  type AgentApproval,
} from '@/domain/models/agent'
import { ApprovalPanel } from '@/features/ai-chat/components/approval/approval-panel'

function approval(
  id: string,
  overrides: Partial<AgentApproval> = {}
): AgentApproval {
  return {
    id,
    runId: 'r-1',
    toolCallId: `tc-${id}`,
    status: AGENT_APPROVAL_STATUS.PENDING,
    proposal: {
      tool: 'memory_write',
      risk: AGENT_TOOL_RISK.WRITE,
      stepId: 'step-1',
      turn: 1,
    },
    expiresAt: new Date(Date.now() + 5 * 60_000).toISOString(),
    ...overrides,
  }
}

describe('ApprovalPanel', () => {
  it('同一步骤多项写操作归组展示，计数与工具调用同源', () => {
    render(
      <ApprovalPanel
        approvals={[approval('a'), approval('b')]}
        onDecide={vi.fn()}
        toolCallCount={3}
      />
    )
    expect(
      screen.getByText(`${AGENT_APPROVAL_COPY.planTitle}（2 项）`)
    ).toBeInTheDocument()
    expect(
      document
        .querySelector('[data-approval-pending-count]')
        ?.getAttribute('data-approval-pending-count')
    ).toBe('2')
    expect(
      document
        .querySelector('[data-approval-tool-count]')
        ?.getAttribute('data-approval-tool-count')
    ).toBe('3')
    // 每项各自一个决策入口（2 张卡的批准按钮），没有批量批准
    expect(screen.getAllByRole('button', { name: '批准执行' })).toHaveLength(2)
    expect(screen.queryByRole('button', { name: /全部批准/ })).not.toBeInTheDocument()
  })

  it('已决 / 过期单收进「已处理」折叠区，不与待审批混排', () => {
    render(
      <ApprovalPanel
        approvals={[
          approval('pending'),
          approval('ok', {
            status: AGENT_APPROVAL_STATUS.APPROVED,
            decidedBy: 1,
            decidedAt: 't',
          }),
          approval('expired', {
            status: AGENT_APPROVAL_STATUS.EXPIRED,
            expiresAt: '2020-01-01T00:00:00Z',
          }),
        ]}
        onDecide={vi.fn()}
      />
    )
    expect(screen.getByText('已处理（2 项）')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '批准执行' })).toHaveLength(1)
  })

  it('加载态与错误态：错误可重试，重试回调被调用', async () => {
    const onRetry = vi.fn()
    const { rerender } = render(
      <ApprovalPanel approvals={[]} loading onDecide={vi.fn()} />
    )
    expect(screen.getByText(AGENT_APPROVAL_COPY.loading)).toBeInTheDocument()

    rerender(
      <ApprovalPanel
        approvals={[]}
        error={AGENT_APPROVAL_COPY.loadFailed}
        onDecide={vi.fn()}
        onRetry={onRetry}
      />
    )
    expect(screen.getByText(AGENT_APPROVAL_COPY.loadFailed)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('无审批单且非加载 / 错误：面板整块不渲染（空态不占位）', () => {
    const { container } = render(
      <ApprovalPanel approvals={[]} onDecide={vi.fn()} />
    )
    expect(
      container.querySelector('[data-agent-approval-panel]')
    ).toBeNull()
  })
})

describe('ApprovalPanel 拆单批次（§9.4.1）', () => {
  /** 同批第 index 张单（batch_total=3，proposal.object_count=21） */
  function batchApproval(
    index: number,
    overrides: Partial<AgentApproval> = {}
  ): AgentApproval {
    return approval(`batch-${index}`, {
      toolCallId: 'tc-batch',
      batchId: 'batch-1',
      batchIndex: index,
      batchTotal: 3,
      proposal: {
        tool: 'tag_group_manage',
        risk: AGENT_TOOL_RISK.WRITE,
        stepId: 'step-1',
        turn: 1,
        arguments: { ids: [`c-${index}`] },
        objectCount: 21,
      },
      objectRef: { kind: 'testcase', ids: [`c-${index}`] },
      ...overrides,
    })
  }

  it('同批 N 张卡按 batchIndex 升序聚组：组头给对象数与 all-or-nothing 提示，每卡标「第 i/N 条」', () => {
    render(
      <ApprovalPanel
        approvals={[batchApproval(3), batchApproval(1), batchApproval(2)]}
        onDecide={vi.fn()}
      />
    )

    expect(
      document.querySelector('[data-approval-batch-header]')?.textContent
    ).toContain('本批 3 张单 · 对象 21 个 · 本批全部批准后才执行')

    const indexes = Array.from(
      document.querySelectorAll('[data-approval-batch-index]')
    ).map((node) => node.getAttribute('data-approval-batch-index'))
    expect(indexes).toEqual(['1/3', '2/3', '3/3'])

    // 决策仍逐张：三张卡各自一个批准按钮，没有批量批准
    expect(screen.getAllByRole('button', { name: '批准执行' })).toHaveLength(3)
    expect(screen.queryByRole('button', { name: /全部批准/ })).not.toBeInTheDocument()
  })

  it('任一单被拒绝：组头显示「本批不执行」，不误导为部分执行', () => {
    render(
      <ApprovalPanel
        approvals={[
          batchApproval(1),
          batchApproval(2, { status: AGENT_APPROVAL_STATUS.REJECTED }),
          batchApproval(3),
        ]}
        onDecide={vi.fn()}
      />
    )

    // 待审批组只剩 2 张，但批次状态按整批算（已决卡被折叠进「已处理」）
    expect(
      document.querySelector('[data-approval-batch-header]')?.textContent
    ).toContain('本批不执行（任一单被拒绝）')
    expect(
      document.querySelector('[data-approval-batch]')?.getAttribute(
        'data-approval-batch-state'
      )
    ).toBe(AGENT_APPROVAL_STATUS.REJECTED)
  })

  it('全部批准：折叠区里组头提示「本批已全部批准，待执行」', async () => {
    render(
      <ApprovalPanel
        approvals={[
          batchApproval(1, { status: AGENT_APPROVAL_STATUS.APPROVED }),
          batchApproval(2, { status: AGENT_APPROVAL_STATUS.APPROVED }),
          batchApproval(3, { status: AGENT_APPROVAL_STATUS.APPROVED }),
        ]}
        onDecide={vi.fn()}
      />
    )

    await userEvent.click(screen.getByText('已处理（3 项）'))
    expect(
      document.querySelector('[data-approval-batch-header]')?.textContent
    ).toContain('本批已全部批准，待执行')
  })

  it('旧单张（无批次字段）不出现批次组头与「第 i/N 条」，渲染与 INT-2472 一致', () => {
    render(<ApprovalPanel approvals={[approval('a'), approval('b')]} onDecide={vi.fn()} />)

    expect(document.querySelector('[data-approval-batch]')).toBeNull()
    expect(document.querySelector('[data-approval-batch-header]')).toBeNull()
    expect(document.querySelector('[data-approval-batch-index]')).toBeNull()
    expect(
      screen.getByText(`${AGENT_APPROVAL_COPY.planTitle}（2 项）`)
    ).toBeInTheDocument()
  })
})

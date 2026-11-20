/**
 * 审批卡单测（INT-2472 §12.2 / §9.4）：
 * 风险等级与提案展示、过期倒计时到点后按钮不可点、决策请求在途时按钮禁用、
 * 已决状态展示决策人与时间。
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  AGENT_APPROVAL_COPY,
  AGENT_APPROVAL_DECISION,
  AGENT_APPROVAL_STATUS,
  AGENT_TOOL_RISK,
  type AgentApproval,
} from '@/domain/models/agent'
import { ApprovalCard } from '@/features/ai-chat/components/approval/approval-card'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

afterEach(() => {
  useAuthStore.setState({ user: null })
})

function buildApproval(overrides: Partial<AgentApproval> = {}): AgentApproval {
  return {
    id: 'ap-1',
    runId: 'r-1',
    toolCallId: 'tc-1',
    status: AGENT_APPROVAL_STATUS.PENDING,
    proposal: {
      tool: 'memory_write',
      risk: AGENT_TOOL_RISK.WRITE,
      stepId: 'step-1',
      turn: 2,
      arguments: { section: 'USER_PROFILE' },
    },
    diff: {
      kind: 'rest_request',
      method: 'POST',
      path: '/api/v1/memory',
      arguments: { section: 'USER_PROFILE' },
    },
    expiresAt: new Date(Date.now() + 10 * 60_000).toISOString(),
    ...overrides,
  }
}

describe('ApprovalCard', () => {
  it('展示提案风险 / 步骤 / 倒计时 / 变更预览，批准回调带 APPROVE', async () => {
    const onDecide = vi.fn().mockResolvedValue(null)
    render(<ApprovalCard approval={buildApproval()} deciding={false} onDecide={onDecide} />)

    expect(screen.getByText('写操作审批')).toBeInTheDocument()
    expect(screen.getByText('写操作')).toBeInTheDocument()
    expect(screen.getByText('待审批')).toBeInTheDocument()
    expect(screen.getByText(/步骤 step-1/)).toBeInTheDocument()
    // 后端 turn 从 0 起，界面展示 1 起（P3-2：不再出现「第 0 轮」）
    expect(screen.getByText(/第 3 轮/)).toBeInTheDocument()
    expect(document.querySelector('[data-approval-countdown]')?.textContent).toContain(
      '剩余'
    )
    expect(document.querySelector('[data-approval-diff]')?.textContent).toContain(
      'POST'
    )

    await userEvent.click(screen.getByRole('button', { name: '批准执行' }))
    expect(onDecide).toHaveBeenCalledTimes(1)
    expect(onDecide).toHaveBeenCalledWith('ap-1', AGENT_APPROVAL_DECISION.APPROVE)
  })

  it('过期后卡片落失效态：按钮禁用，不能再批准', () => {
    render(
      <ApprovalCard
        approval={buildApproval({
          expiresAt: new Date(Date.now() - 60_000).toISOString(),
        })}
        deciding={false}
        onDecide={vi.fn()}
      />
    )

    expect(screen.getByText('已过期')).toBeInTheDocument()
    expect(screen.getAllByText(/提案已过期/).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: '批准执行' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '拒绝' })).toBeDisabled()
  })

  it('决策在途（deciding=true）：按钮禁用并展示进行中文案', () => {
    render(<ApprovalCard approval={buildApproval()} deciding onDecide={vi.fn()} />)
    expect(screen.getByRole('button', { name: '批准执行' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '拒绝' })).toBeDisabled()
  })

  it('已批准：不渲染决策按钮，决策人是自己时显示「我」，展示执行提示', () => {
    useAuthStore.setState({
      user: {
        id: '7',
        username: 'dev_user',
        displayName: 'dev_user',
        roleName: '管理员',
        permissions: ['*'],
      },
    })
    render(
      <ApprovalCard
        approval={buildApproval({
          status: AGENT_APPROVAL_STATUS.APPROVED,
          decidedBy: 7,
          decidedAt: '2026-11-14T02:03:00Z',
        })}
        deciding={false}
        onDecide={vi.fn()}
      />
    )
    expect(screen.queryByRole('button', { name: '批准执行' })).not.toBeInTheDocument()
    expect(screen.getByText('已批准')).toBeInTheDocument()
    // 决策人数字 id 不直出（P3-4）
    expect(document.querySelector('[data-approval-decided]')?.textContent).toContain(
      '决策人 我'
    )
    expect(screen.getByText(/Agent 将在服务端执行该写操作/)).toBeInTheDocument()
  })

  it('run 已收口：已批准卡不再展示未来时的执行提示（P3-5）', () => {
    render(
      <ApprovalCard
        approval={buildApproval({
          status: AGENT_APPROVAL_STATUS.APPROVED,
          decidedBy: 7,
          decidedAt: '2026-11-14T02:03:00Z',
        })}
        deciding={false}
        onDecide={vi.fn()}
        runFinished
      />
    )
    expect(screen.getByText('已批准')).toBeInTheDocument()
    expect(
      screen.queryByText(/Agent 将在服务端执行该写操作/)
    ).not.toBeInTheDocument()
  })

  it('长步骤 UUID 截断展示、turn=0 显示第 1 轮（P3-2 / P3-3）', () => {
    render(
      <ApprovalCard
        approval={buildApproval({
          proposal: {
            tool: 'memory_write',
            risk: AGENT_TOOL_RISK.WRITE,
            stepId: '8dd2ee8d-1c4e-4b7a-9f00-112233445566',
            turn: 0,
          },
        })}
        deciding={false}
        onDecide={vi.fn()}
      />
    )
    expect(screen.queryByText(/8dd2ee8d-1c4e-4b7a/)).not.toBeInTheDocument()
    expect(screen.getByText(/步骤 8dd2ee8d…/)).toBeInTheDocument()
    expect(screen.getByText('第 1 轮')).toBeInTheDocument()
  })

  it('DESTRUCTIVE：风险徽标为高危操作（永远单条，卡片不出现批量按钮）', () => {
    render(
      <ApprovalCard
        approval={buildApproval({
          proposal: {
            tool: 'report_batch_delete',
            risk: AGENT_TOOL_RISK.DESTRUCTIVE,
          },
        })}
        deciding={false}
        onDecide={vi.fn()}
      />
    )
    expect(screen.getByText('高危操作')).toBeInTheDocument()
    expect(document.querySelector('[data-approval-risk]')?.getAttribute(
      'data-approval-risk'
    )).toBe(AGENT_TOOL_RISK.DESTRUCTIVE)
    // 只有单条决策入口，没有「全部批准」之类的批量按钮
    expect(screen.queryByRole('button', { name: /全部/ })).not.toBeInTheDocument()
  })

  it('DESTRUCTIVE：批准必须先过二次确认，确认后带 confirm=true（INT-2467）', async () => {
    const onDecide = vi.fn().mockResolvedValue(null)
    render(
      <ApprovalCard
        approval={buildApproval({
          proposal: {
            tool: 'device_control',
            risk: AGENT_TOOL_RISK.DESTRUCTIVE,
            arguments: { action: 'reboot', device_id: 7 },
          },
        })}
        deciding={false}
        onDecide={onDecide}
      />
    )

    await userEvent.click(screen.getByRole('button', { name: '批准执行' }))
    // 单击不直接发请求：先弹二次确认
    expect(onDecide).not.toHaveBeenCalled()
    expect(screen.getByText('确认执行高危操作？')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '确认批准' }))
    expect(onDecide).toHaveBeenCalledTimes(1)
    expect(onDecide).toHaveBeenCalledWith(
      'ap-1',
      AGENT_APPROVAL_DECISION.APPROVE,
      true
    )
  })

  it('>20 对象批量写：强制逐项核对，全部勾选后才能批准（不带 confirm）', async () => {
    const onDecide = vi.fn().mockResolvedValue(null)
    const deviceIds = Array.from({ length: 21 }, (_, index) => index + 1)
    render(
      <ApprovalCard
        approval={buildApproval({
          proposal: {
            tool: 'device_control',
            risk: AGENT_TOOL_RISK.WRITE,
            arguments: { action: 'batch', device_ids: deviceIds },
          },
        })}
        deciding={false}
        onDecide={onDecide}
      />
    )

    expect(screen.getByText('影响对象 21')).toBeInTheDocument()
    expect(document.querySelector('[data-approval-batch-hint]')?.textContent).toContain(
      '超过单次审批上限'
    )

    await userEvent.click(screen.getByRole('button', { name: '批准执行' }))
    expect(onDecide).not.toHaveBeenCalled()

    const confirmButton = screen.getByRole('button', { name: '逐项核对后批准' })
    expect(confirmButton).toBeDisabled()

    const checkboxes = screen.getAllByRole('checkbox')
    expect(checkboxes).toHaveLength(21)
    for (const checkbox of checkboxes) {
      await userEvent.click(checkbox)
    }
    expect(confirmButton).not.toBeDisabled()

    await userEvent.click(confirmButton)
    expect(onDecide).toHaveBeenCalledWith(
      'ap-1',
      AGENT_APPROVAL_DECISION.APPROVE
    )
  })

  it('>20 对象但 DESTRUCTIVE：逐项核对 + confirm=true 一起生效（§9.4 永远单条）', async () => {
    const onDecide = vi.fn().mockResolvedValue(null)
    render(
      <ApprovalCard
        approval={buildApproval({
          proposal: {
            tool: 'device_control',
            risk: AGENT_TOOL_RISK.DESTRUCTIVE,
            arguments: {
              action: 'batch',
              device_ids: Array.from({ length: 25 }, (_, index) => index + 1),
            },
          },
        })}
        deciding={false}
        onDecide={onDecide}
      />
    )

    await userEvent.click(screen.getByRole('button', { name: '批准执行' }))
    const confirmButton = screen.getByRole('button', { name: '确认批准' })
    expect(confirmButton).toBeDisabled()
    for (const checkbox of screen.getAllByRole('checkbox')) {
      await userEvent.click(checkbox)
    }
    await userEvent.click(confirmButton)
    expect(onDecide).toHaveBeenCalledWith('ap-1', 'APPROVE', true)
  })

  it('风险未知（proposal 无 risk）：按高危处理，批准也要二次确认', async () => {
    const onDecide = vi.fn().mockResolvedValue(null)
    render(
      <ApprovalCard
        approval={buildApproval({
          proposal: { tool: 'unknown_write_tool' },
        })}
        deciding={false}
        onDecide={onDecide}
      />
    )

    await userEvent.click(screen.getByRole('button', { name: '批准执行' }))
    expect(onDecide).not.toHaveBeenCalled()
    expect(screen.getByText('二次确认')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '确认批准' }))
    expect(onDecide).toHaveBeenCalledWith('ap-1', 'APPROVE', true)
  })

  it('服务端 400 要求补确认（APPROVAL_CONFIRMATION_REQUIRED）：补弹确认后带 confirm 重发', async () => {
    const onDecide = vi
      .fn()
      .mockResolvedValueOnce(AGENT_APPROVAL_COPY.confirmRequired)
      .mockResolvedValueOnce(null)
    render(
      <ApprovalCard approval={buildApproval()} deciding={false} onDecide={onDecide} />
    )

    await userEvent.click(screen.getByRole('button', { name: '批准执行' }))
    expect(onDecide).toHaveBeenCalledTimes(1)
    expect(onDecide).toHaveBeenLastCalledWith('ap-1', 'APPROVE')

    // 400 后决策未落库：卡片弹二次确认，确认后带 confirm=true 重发
    await waitFor(() => {
      expect(screen.getByText('二次确认')).toBeInTheDocument()
    })
    await userEvent.click(screen.getByRole('button', { name: '确认批准' }))
    expect(onDecide).toHaveBeenCalledTimes(2)
    expect(onDecide).toHaveBeenLastCalledWith('ap-1', 'APPROVE', true)
  })
})

describe('ApprovalCard 拆单批次（§9.4.1）', () => {
  /** 同批第 index/N 张单：参数已收窄到本单对象 */
  function batchedApproval(overrides: Partial<AgentApproval> = {}): AgentApproval {
    return buildApproval({
      batchId: 'batch-1',
      batchIndex: 2,
      batchTotal: 3,
      proposal: {
        tool: 'tag_group_manage',
        risk: AGENT_TOOL_RISK.WRITE,
        arguments: { ids: ['c-2'] },
        objectCount: 21,
      },
      objectRef: { kind: 'testcase', ids: ['c-2'] },
      ...overrides,
    })
  }

  it('批次卡展示「本批第 i/N 条」、本单对象摘要与 all-or-nothing 提示', () => {
    render(
      <ApprovalCard approval={batchedApproval()} deciding={false} onDecide={vi.fn()} />
    )
    expect(screen.getByText('本批第 2/3 条')).toBeInTheDocument()
    expect(
      document.querySelector('[data-approval-object-ref]')?.textContent
    ).toContain('testcase · c-2')
    expect(
      document.querySelector('[data-approval-batch-pending]')?.textContent
    ).toBe('本批全部批准后才执行')
    // 拆单卡不再出现「影响对象超过单次审批上限」的逐项核对提示
    expect(document.querySelector('[data-approval-batch-hint]')).toBeNull()
  })

  it('拆单卡即使参数 >20 也不再触发逐项核对：单击批准直接发请求（不弹确认）', async () => {
    const onDecide = vi.fn().mockResolvedValue(null)
    render(
      <ApprovalCard
        approval={batchedApproval({
          proposal: {
            tool: 'tag_group_manage',
            risk: AGENT_TOOL_RISK.WRITE,
            arguments: {
              ids: Array.from({ length: 21 }, (_, index) => `c-${index}`),
            },
            objectCount: 21,
          },
        })}
        deciding={false}
        onDecide={onDecide}
      />
    )

    await userEvent.click(screen.getByRole('button', { name: '批准执行' }))
    // 拆单由后端保证 all-or-nothing，卡片本身不再要求逐项勾选
    expect(onDecide).toHaveBeenCalledTimes(1)
    expect(onDecide).toHaveBeenCalledWith('ap-1', AGENT_APPROVAL_DECISION.APPROVE)
  })

  it('已批准但同批仍有待审批：提示「本批全部批准后才执行」，不说已在服务端执行', () => {
    render(
      <ApprovalCard
        approval={batchedApproval({
          status: AGENT_APPROVAL_STATUS.APPROVED,
          decidedBy: 7,
          decidedAt: '2026-11-14T02:03:00Z',
        })}
        batchState={AGENT_APPROVAL_STATUS.PENDING}
        deciding={false}
        onDecide={vi.fn()}
      />
    )
    expect(screen.getByText('本批全部批准后才执行')).toBeInTheDocument()
    expect(
      screen.queryByText(/Agent 将在服务端执行该写操作/)
    ).not.toBeInTheDocument()
  })

  it('本批全部批准：提示待执行；本批不执行（拒绝）：不展示逐张已拒绝的局部语义', () => {
    const { rerender } = render(
      <ApprovalCard
        approval={batchedApproval({ status: AGENT_APPROVAL_STATUS.APPROVED })}
        batchState={AGENT_APPROVAL_STATUS.APPROVED}
        deciding={false}
        onDecide={vi.fn()}
      />
    )
    expect(screen.getByText('本批已全部批准，待执行')).toBeInTheDocument()

    rerender(
      <ApprovalCard
        approval={batchedApproval({ status: AGENT_APPROVAL_STATUS.REJECTED })}
        batchState={AGENT_APPROVAL_STATUS.REJECTED}
        deciding={false}
        onDecide={vi.fn()}
      />
    )
    expect(screen.getByText('本批不执行（任一单被拒绝）')).toBeInTheDocument()
  })
})

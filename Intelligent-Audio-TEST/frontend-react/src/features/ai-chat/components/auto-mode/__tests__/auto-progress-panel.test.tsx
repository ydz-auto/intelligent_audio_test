/**
 * Auto 进度面板单测（INT-2474 §9.4）。
 * 关注点：非 Auto 不渲染；进度 / 预算水位 / 产物；暂停点给继续与结束；
 * 终态不误导（超预算 / 熔断不是成功）；Auto 下不提供「全部自动批准」。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import {
  AGENT_AUTO_COPY,
  AGENT_RUN_PAUSE_REASON,
  AGENT_RUN_STATUS,
  type AgentAutoPause,
  type AgentAutoProgress,
  type AgentRun,
} from '@/domain/models/agent'
import { AutoProgressPanel } from '@/features/ai-chat/components/auto-mode/auto-progress-panel'

function progress(overrides: Partial<AgentAutoProgress> = {}): AgentAutoProgress {
  return {
    step: 3,
    phase: 'step',
    goal: '把回归测试全跑一遍',
    plan: '先读用例，再起任务，最后对比结果',
    usage: {
      rounds: 3,
      toolCalls: 6,
      tokens: 1200,
      elapsedSeconds: 125,
      outputBytes: 1024,
    },
    limits: {
      maxRounds: 60,
      maxToolCalls: 120,
      maxDurationSeconds: 1800,
      maxOutputBytes: 20 * 1024 * 1024,
    },
    ratio: 0.05,
    consecutiveFailures: 0,
    artifactCount: 1,
    artifacts: [{ id: 'a-1', kind: 'report', uri: 's3://bucket/report-1' }],
    ...overrides,
  }
}

function run(overrides: Partial<AgentRun> = {}): AgentRun {
  return {
    id: 'r-1',
    sessionId: 's-1',
    status: AGENT_RUN_STATUS.RUNNING,
    mode: 'auto',
    ...overrides,
  }
}

function pause(overrides: Partial<AgentAutoPause> = {}): AgentAutoPause {
  return {
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
    ...overrides,
  }
}

describe('AutoProgressPanel', () => {
  it('非 Auto run 不渲染', () => {
    const { container } = render(
      <AutoProgressPanel
        pause={null}
        progress={null}
        run={run({ mode: 'chat' })}
      />
    )
    expect(container.querySelector('[data-auto-progress]')).toBeNull()
  })

  it('运行中：展示目标 / 步骤 / 预算水位 / 产物，且没有继续按钮', () => {
    const { container } = render(
      <AutoProgressPanel
        pause={null}
        progress={progress()}
        run={run()}
      />
    )

    expect(screen.getByText(AGENT_AUTO_COPY.progressTitle)).toBeTruthy()
    expect(screen.getByText(/把回归测试全跑一遍/)).toBeTruthy()
    expect(container.querySelector('[data-auto-step]')?.textContent).toContain(
      '当前步骤 3 步'
    )
    expect(container.querySelector('[data-auto-ratio]')?.textContent).toBe('5%')
    // 五维预算行（未启用的 token 也保留行，但不显示上限）
    expect(screen.getByText('轮次')).toBeTruthy()
    expect(screen.getByText('工具调用')).toBeTruthy()
    // 产物摘要
    expect(
      container.querySelector('[data-auto-artifact-count]')?.getAttribute(
        'data-auto-artifact-count'
      )
    ).toBe('1')
    expect(screen.getByText(/s3:\/\/bucket\/report-1/)).toBeTruthy()
    expect(container.querySelector('[data-auto-resume]')).toBeNull()
  })

  it('空产物给出「暂无产物」', () => {
    render(
      <AutoProgressPanel
        pause={null}
        progress={progress({ artifactCount: 0, artifacts: [] })}
        run={run()}
      />
    )
    expect(screen.getByText(AGENT_AUTO_COPY.progressNoArtifacts)).toBeTruthy()
  })

  it('暂停（预算阈值）：给原因 + 继续 / 结束按钮，点击回调', () => {
    const onResume = vi.fn()
    const onStop = vi.fn()
    const { container } = render(
      <AutoProgressPanel
        onResume={onResume}
        onStop={onStop}
        pause={pause()}
        progress={progress({ ratio: 0.8 })}
        run={run({ status: AGENT_RUN_STATUS.WAITING_APPROVAL })}
      />
    )

    expect(container.querySelector('[data-auto-paused]')?.getAttribute(
      'data-auto-paused'
    )).toBe('true')
    expect(
      container.querySelector('[data-auto-pause-reason]')?.getAttribute(
        'data-auto-pause-reason'
      )
    ).toBe(AGENT_RUN_PAUSE_REASON.BUDGET_THRESHOLD)
    expect(screen.getByText(AGENT_AUTO_COPY.pausedBudget)).toBeTruthy()

    fireEvent.click(screen.getByText(AGENT_AUTO_COPY.resume))
    expect(onResume).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByText(AGENT_AUTO_COPY.stop))
    expect(onStop).toHaveBeenCalledTimes(1)
  })

  it('暂停且仍有待审批提案：禁用继续、提示逐条审批、无「全部自动批准」入口', () => {
    const { container } = render(
      <AutoProgressPanel
        onResume={() => undefined}
        pause={pause({ reason: AGENT_RUN_PAUSE_REASON.CONSECUTIVE_TOOL_FAILURES })}
        pendingApprovalCount={2}
        progress={progress()}
        run={run({ status: AGENT_RUN_STATUS.WAITING_APPROVAL })}
      />
    )

    expect(screen.getByText(/连续 2 次工具失败/)).toBeTruthy()
    const resumeButton = container.querySelector(
      '[data-auto-resume]'
    ) as HTMLButtonElement
    expect(resumeButton.disabled).toBe(true)
    expect(screen.getByText(new RegExp(AGENT_AUTO_COPY.approvalsHint))).toBeTruthy()
    expect(
      container.querySelector('[data-auto-approvals-count]')?.getAttribute(
        'data-auto-approvals-count'
      )
    ).toBe('2')
    // 红线：不提供「全部自动批准」入口（提示文案里说明「不提供」不算入口）
    expect(
      screen.queryAllByRole('button', { name: /全部自动批准/ })
    ).toHaveLength(0)
  })

  it('超预算终态：显示「超出预算已停止」，不是成功，且无可操作的继续按钮', () => {
    const { container } = render(
      <AutoProgressPanel
        pause={null}
        progress={progress({ ratio: 1 })}
        run={run({ status: AGENT_RUN_STATUS.BUDGET_EXCEEDED, error: 'BUDGET_EXCEEDED' })}
      />
    )

    expect(container.querySelector('[data-auto-terminal]')?.getAttribute(
      'data-auto-terminal'
    )).toBe('budget_exceeded')
    expect(screen.getAllByText(AGENT_AUTO_COPY.budgetExceededTitle).length).toBeGreaterThan(0)
    expect(screen.queryByText(AGENT_AUTO_COPY.finishedTitle)).toBeNull()
    expect(container.querySelector('[data-auto-resume]')).toBeNull()
  })

  it('熔断终态：显示「已熔断停止」', () => {
    const { container } = render(
      <AutoProgressPanel
        pause={null}
        progress={progress({ consecutiveFailures: 3 })}
        run={run({
          status: AGENT_RUN_STATUS.FAILED,
          error: 'CONSECUTIVE_TOOL_FAILURES',
        })}
      />
    )
    expect(container.querySelector('[data-auto-terminal]')?.getAttribute(
      'data-auto-terminal'
    )).toBe('circuit_break')
    expect(screen.getAllByText(AGENT_AUTO_COPY.circuitTitle).length).toBeGreaterThan(0)
    // 内部错误码收进「查看详情」，不直接铺在用户文案里（P3-4）
    const code = container.querySelector('[data-auto-error-code]')
    expect(code?.textContent).toBe('CONSECUTIVE_TOOL_FAILURES')
    expect(code?.closest('details')).not.toBeNull()
  })

  it('刷新恢复后继续：面板给「等待服务端结果」，不是无限「正在收集步骤进度」', () => {
    render(
      <AutoProgressPanel
        pause={null}
        progress={null}
        run={run({ status: AGENT_RUN_STATUS.RUNNING })}
        tracking
      />
    )
    expect(screen.getByRole('status').textContent).toContain(AGENT_AUTO_COPY.tracking)
    expect(screen.queryByText('正在收集步骤进度…')).toBeNull()
  })

  it('终态下不再重复底部红色 alert（P3-4）', () => {
    render(
      <AutoProgressPanel
        error='Agent 运行失败，请重试'
        pause={null}
        progress={progress()}
        run={run({
          status: AGENT_RUN_STATUS.FAILED,
          error: 'CONSECUTIVE_TOOL_FAILURES',
        })}
      />
    )
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('运行错误单独提示（不伪装成终态徽标）', () => {
    render(
      <AutoProgressPanel
        error='Agent 事件流中断，请重试'
        pause={null}
        progress={progress()}
        run={run()}
      />
    )
    expect(screen.getByRole('alert').textContent).toContain('事件流中断')
  })
})

/**
 * 发布门槛面板（INT-2550 打回修复）：门槛未达标时发布按钮必须禁用。
 *
 * 门槛只在发布动作后才有结果；一旦服务端返回 `passed=false`，按钮置灰、
 * 文案保持「发布」，并显示「只能留作草稿，不参与自动触发」。
 * 重新保存会清空本次门槛结果，按钮随之恢复可点。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { SkillGate } from '@/domain/models/agentSkill'
import { SkillGatePanel } from '@/features/agent-skills/components/skill-gate-panel'

const UNMET_GATE: SkillGate = {
  goldenTasks: 0,
  passed: false,
  failures: ['golden tasks 0 条，未达发布门槛 3 条'],
  note: '',
}

const MET_GATE: SkillGate = {
  goldenTasks: 3,
  passed: true,
  failures: [],
  note: '',
}

function props(overrides: Partial<React.ComponentProps<typeof SkillGatePanel>> = {}) {
  return {
    gate: null as SkillGate | null,
    pending: false,
    errorMessage: null,
    onPublish: vi.fn(),
    publishable: true,
    unmet: false,
    ...overrides,
  }
}

describe('SkillGatePanel 发布按钮门槛（INT-2550）', () => {
  it('门槛未达标：发布按钮禁用，文案保持「发布」，面板说明只能留作草稿', () => {
    render(<SkillGatePanel {...props({ gate: UNMET_GATE, unmet: true })} />)

    const button = screen.getByTestId('skill-publish-button')
    expect(button).toBeDisabled()
    expect(button).toHaveTextContent('发布')
    expect(button).not.toHaveTextContent('重新尝试发布')
    expect(screen.getByTestId('skill-gate-unmet')).toHaveTextContent(
      '只能留作草稿，不参与自动触发'
    )
    expect(screen.getByText('golden tasks 0 条，未达发布门槛 3 条')).toBeInTheDocument()
  })

  it('门槛未达标：点击不会触发发布', () => {
    const onPublish = vi.fn()
    render(
      <SkillGatePanel
        {...props({ gate: UNMET_GATE, unmet: true, onPublish })}
      />
    )

    screen.getByTestId('skill-publish-button').click()
    expect(onPublish).not.toHaveBeenCalled()
  })

  it('门槛达标：发布按钮可点', () => {
    render(<SkillGatePanel {...props({ gate: MET_GATE })} />)

    expect(screen.getByTestId('skill-publish-button')).toBeEnabled()
  })

  it('尚未检查门槛：发布按钮可点（发起检查）', () => {
    render(<SkillGatePanel {...props()} />)

    expect(screen.getByTestId('skill-publish-button')).toBeEnabled()
  })

  it('发布进行中：按钮禁用', () => {
    render(<SkillGatePanel {...props({ pending: true })} />)

    expect(screen.getByTestId('skill-publish-button')).toBeDisabled()
  })
})

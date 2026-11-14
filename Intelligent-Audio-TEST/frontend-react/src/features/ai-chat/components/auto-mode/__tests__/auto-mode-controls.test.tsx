/**
 * Auto 入口与预算设置单测（INT-2474 §9.4）。
 * 关注点：模式切换回调与选中态；预算输入实时回写（合法值）、非法值标红且不提交。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AGENT_AUTO_COPY } from '@/domain/models/agent'
import { AutoBudgetSettings } from '@/features/ai-chat/components/auto-mode/auto-budget-settings'
import { AutoModeSwitcher } from '@/features/ai-chat/components/auto-mode/auto-mode-switcher'

describe('AutoModeSwitcher', () => {
  it('默认对话选中；点 Auto 触发模式切换', () => {
    const onModeChange = vi.fn()
    render(<AutoModeSwitcher mode='chat' onModeChange={onModeChange} />)

    const chatButton = screen.getByText(AGENT_AUTO_COPY.modeChat).closest('button')
    const autoButton = screen.getByText(AGENT_AUTO_COPY.modeAuto).closest('button')
    expect(chatButton?.getAttribute('aria-checked')).toBe('true')
    expect(autoButton?.getAttribute('aria-checked')).toBe('false')

    fireEvent.click(autoButton as HTMLButtonElement)
    expect(onModeChange).toHaveBeenCalledWith('auto')
  })

  it('禁用时点击不触发切换', () => {
    const onModeChange = vi.fn()
    render(<AutoModeSwitcher disabled mode='chat' onModeChange={onModeChange} />)
    fireEvent.click(
      screen.getByText(AGENT_AUTO_COPY.modeAuto).closest('button') as HTMLButtonElement
    )
    expect(onModeChange).not.toHaveBeenCalled()
  })
})

describe('AutoBudgetSettings', () => {
  it('留空默认展示五个维度 + 服务端默认口径说明', () => {
    const { container } = render(
      <AutoBudgetSettings budget={undefined} onBudgetChange={() => undefined} />
    )
    expect(container.querySelector('[data-auto-budget-settings]')).toBeTruthy()
    expect(screen.getByText(AGENT_AUTO_COPY.budgetTitle)).toBeTruthy()
    expect(screen.getByText(AGENT_AUTO_COPY.budgetDefaultHint)).toBeTruthy()
    expect(container.querySelectorAll('input')).toHaveLength(5)
  })

  it('输入轮次 20 → 回写预算（分钟 / MB 由草稿层换算）', () => {
    const onBudgetChange = vi.fn()
    const { container } = render(
      <AutoBudgetSettings budget={undefined} onBudgetChange={onBudgetChange} />
    )
    const roundsInput = container.querySelector('input') as HTMLInputElement

    fireEvent.change(roundsInput, { target: { value: '20' } })
    expect(onBudgetChange).toHaveBeenLastCalledWith({ maxRounds: 20 })
  })

  it('非法输入（0）标红且不提交非法预算', () => {
    const onBudgetChange = vi.fn()
    const { container } = render(
      <AutoBudgetSettings budget={undefined} onBudgetChange={onBudgetChange} />
    )
    const roundsInput = container.querySelector('input') as HTMLInputElement

    fireEvent.change(roundsInput, { target: { value: '0' } })

    expect(roundsInput.getAttribute('aria-invalid')).toBe('true')
    expect(screen.getByText(AGENT_AUTO_COPY.budgetInvalid)).toBeTruthy()
    expect(onBudgetChange).toHaveBeenLastCalledWith(undefined)
  })

  it('外部预算变化同步到输入框（两宿主同一份 config）', () => {
    const { container, rerender } = render(
      <AutoBudgetSettings budget={undefined} onBudgetChange={() => undefined} />
    )
    rerender(
      <AutoBudgetSettings
        budget={{ maxRounds: 30, maxDurationSeconds: 900 }}
        onBudgetChange={() => undefined}
      />
    )
    const inputs = container.querySelectorAll('input')
    expect((inputs[0] as HTMLInputElement).value).toBe('30')
    expect((inputs[3] as HTMLInputElement).value).toBe('15')
  })
})

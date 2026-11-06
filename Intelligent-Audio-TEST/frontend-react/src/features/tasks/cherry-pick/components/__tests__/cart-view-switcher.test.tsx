/**
 * 购物车视图切换器测试（18_挑选合并交互重设计.md §4.2，INT-1128）。
 * 负责人 2026-10-24 口径：结果类型只有一种（真实库目前全为 default）时不渲染
 * 「结果类型视图」按钮，其余视图按钮保持。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { CartViewSwitcher } from '@/features/tasks/cherry-pick/components/cart-view-switcher'

describe('CartViewSwitcher（结果类型视图按钮显隐）', () => {
  it('默认渲染任务/用例/设备/结果类型四视图', () => {
    render(<CartViewSwitcher view='task' onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /任务视图/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /用例视图/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /设备视图/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /结果类型视图/ })).toBeTruthy()
  })

  it('showResultType=false → 不渲染结果类型视图按钮，其余三视图保留', () => {
    render(<CartViewSwitcher view='task' onChange={vi.fn()} showResultType={false} />)
    expect(screen.getByRole('button', { name: /任务视图/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /用例视图/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /设备视图/ })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /结果类型视图/ })).toBeNull()
  })
})

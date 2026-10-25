/**
 * 批量浮条「标记颜色」菜单（INT-1944）。
 * base-ui 的 Menu.GroupLabel 必须挂在 Menu.Group 下：未包裹时点开菜单，
 * popup 渲染即抛错，被根路由 errorComponent（GeneralError）接住 → 整页 500、
 * 菜单不出、批量标记一次也写不进库。本用例锁住「点开即出四色菜单」。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { LogsBulkActions } from '@/features/logs/components/logs-bulk-actions'

const noop = () => {}

function renderBar() {
  return render(
    <LogsBulkActions
      count={2}
      canManage
      onBatchMark={noop}
      onCopySelected={noop}
      onExportSelected={noop}
    />
  )
}

describe('LogsBulkActions 标记颜色菜单', () => {
  it('点开「标记颜色」即渲染黄/红/绿/蓝四色菜单', async () => {
    const user = userEvent.setup()
    renderBar()

    await user.click(screen.getByRole('button', { name: '标记颜色' }))

    expect(await screen.findByText('选择标记颜色')).toBeInTheDocument()
    for (const label of ['黄色', '红色', '绿色', '蓝色']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('选色回传云端标记值（yellow/red/green/blue）', async () => {
    const user = userEvent.setup()
    const marks: string[] = []
    render(
      <LogsBulkActions
        count={2}
        canManage
        onBatchMark={(mark) => marks.push(mark)}
        onCopySelected={noop}
        onExportSelected={noop}
      />
    )

    await user.click(screen.getByRole('button', { name: '标记颜色' }))
    await user.click(await screen.findByText('红色'))

    expect(marks).toEqual(['red'])
  })
})

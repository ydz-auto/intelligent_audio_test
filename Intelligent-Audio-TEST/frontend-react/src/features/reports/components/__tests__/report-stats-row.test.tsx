/**
 * 报告域组件测试——ReportStatsRow 统计徽章行（规范 §3.4）：
 * 加载骨架 / 计数徽章 / 快速筛选回调 / 选中态。
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ReportStatsRow } from '@/features/reports/components/report-stats-row'
import type { ReportCounts } from '@/domain/models/report'

const counts: ReportCounts = {
  all: 42,
  published: 30,
  draft: 10,
  comparison: 2,
}

describe('ReportStatsRow', () => {
  it('加载中且无数据时渲染骨架行', () => {
    const { container } = render(
      <ReportStatsRow isLoading onQuickFilter={vi.fn()} />
    )
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
    expect(
      container.querySelectorAll('[data-slot="skeleton"]').length
    ).toBeGreaterThanOrEqual(1)
  })

  it('渲染四枚计数徽章', () => {
    render(<ReportStatsRow counts={counts} onQuickFilter={vi.fn()} />)
    expect(screen.getByRole('button', { name: /全部报告/ })).toHaveTextContent(
      '42'
    )
    expect(screen.getByRole('button', { name: /已发布/ })).toHaveTextContent(
      '30'
    )
    expect(screen.getByRole('button', { name: /草稿/ })).toHaveTextContent(
      '10'
    )
    expect(
      screen.getByRole('button', { name: /对比报告/ })
    ).toHaveTextContent('2')
  })

  it('点击徽章触发 onQuickFilter', async () => {
    const user = userEvent.setup()
    const onQuickFilter = vi.fn()
    render(
      <ReportStatsRow counts={counts} onQuickFilter={onQuickFilter} />
    )
    await user.click(screen.getByRole('button', { name: /已发布/ }))
    expect(onQuickFilter).toHaveBeenCalledWith('published')
    await user.click(screen.getByRole('button', { name: /草稿/ }))
    expect(onQuickFilter).toHaveBeenCalledWith('draft')
  })

  it('activeFilter 命中徽章置选中态', () => {
    render(
      <ReportStatsRow
        counts={counts}
        activeFilter={{ status: 'draft' }}
        onQuickFilter={vi.fn()}
      />
    )
    const draft = screen.getByRole('button', { name: /草稿/ })
    expect(draft).toHaveAttribute('aria-pressed', 'true')
    expect(
      within(draft).getByText('10')
    ).toBeInTheDocument()
  })

  it('对比类型筛选同时匹配 comparison 与 secondary_comparison', () => {
    render(
      <ReportStatsRow
        counts={counts}
        activeFilter={{ type: 'comparison' }}
        onQuickFilter={vi.fn()}
      />
    )
    expect(
      screen.getByRole('button', { name: /对比报告/ })
    ).toHaveAttribute('aria-pressed', 'true')
  })
})

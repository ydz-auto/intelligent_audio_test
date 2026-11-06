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
  // legacy 汇总口径（comparison + secondary_comparison），与徽章点击结果无关
  comparison: 4,
  types: { task: 38, comparison: 1, secondary_comparison: 3, benchmark: 0 },
  favorite: 0,
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
    ).toHaveTextContent('1')
  })

  it('对比报告徽章读 types.comparison，不用 legacy 汇总计数（与点击结果/类型 chips 同口径）', () => {
    render(<ReportStatsRow counts={counts} onQuickFilter={vi.fn()} />)
    const badge = screen.getByRole('button', { name: /对比报告/ })
    // types.comparison = 1；legacy counts.comparison = 4 不得出现
    expect(badge).toHaveTextContent('1')
    expect(within(badge).queryByText('4')).toBeNull()
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

  it('type=comparison 时对比报告徽章置选中态（二次对比独立经类型 chips）', () => {
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

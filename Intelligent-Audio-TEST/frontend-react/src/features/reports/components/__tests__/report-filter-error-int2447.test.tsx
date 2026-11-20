/**
 * INT-2447 回归锁：
 * - P3-1 报告中心 / 报告展示页「时间范围」Select 回显中文 label（修复前 Base UI 直出英文 value `all`），
 *   任意取值（今日）也解析成 label；报告展示页顶部 Badge 同样不落英文 value。
 * - P3-1 残余：报告中心「高级搜索」折叠区 设备类型 / 创建者 / 时间范围 三个 Select 同样回显中文
 *   label（修复前 `all` / `smart_speaker` / `today`）。
 * - P3-2 报告列表错误态统一走公共 ErrorState：红色 AlertTriangle + 「报告列表加载失败」+ 「重试」，
 *   不再手搓 Empty（排序图标 ↑↓ / 按钮「请重试」）。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ReportAdvancedSearch } from '@/features/reports/components/report-advanced-search'
import { ReportHero } from '@/features/reports/components/report-hero'
import { ReportCardGrid } from '@/features/reports/components/report-card-grid'
import { ReportsTable } from '@/features/reports/components/reports-table'
import { ReportShowcaseHero } from '@/features/reports-showcase/components/report-showcase-hero'
import type { ReportTimeRange } from '@/domain/models/report'

const hasPermission = () => true

function reportHero(timeRange?: ReportTimeRange) {
  return render(
    <ReportHero
      totalReports={60}
      draftCount={55}
      publishedCount={5}
      typeCounts={{ all: 60, task: 56, comparison: 1, secondary_comparison: 3, benchmark: 0 }}
      search=''
      onSearchChange={vi.fn()}
      onTypeChange={vi.fn()}
      onStatusChange={vi.fn()}
      timeRange={timeRange}
      onTimeRangeChange={vi.fn()}
      onCustomRangeChange={vi.fn()}
      hasActiveFilters={false}
      onClearAll={vi.fn()}
    />
  )
}

function showcaseHero(timeRange?: ReportTimeRange) {
  return render(
    <ReportShowcaseHero
      search=''
      onSearchChange={vi.fn()}
      type={undefined}
      onTypeChange={vi.fn()}
      timeRange={timeRange}
      onTimeRangeChange={vi.fn()}
      onCustomRangeChange={vi.fn()}
      hasActiveFilters={false}
      onClearAll={vi.fn()}
    />
  )
}

function errorTable() {
  return render(
    <ReportsTable
      items={[]}
      hasError
      hasActiveFilters={false}
      trashMode={false}
      selectedIds={[]}
      onToggleRow={vi.fn()}
      onToggleAll={vi.fn()}
      hasPermission={hasPermission}
      onRowAction={vi.fn()}
      onRowClick={vi.fn()}
      onClearFilters={vi.fn()}
      onRetry={vi.fn()}
    />
  )
}

function errorCardGrid() {
  return render(
    <ReportCardGrid
      items={[]}
      hasError
      trashMode={false}
      hasPermission={hasPermission}
      onRowAction={vi.fn()}
      onCardClick={vi.fn()}
      onRetry={vi.fn()}
    />
  )
}

describe('INT-2447 P3-1 时间范围筛选文案', () => {
  it('报告中心默认显示「全部时间」，不落英文 value all', () => {
    reportHero()
    const trigger = screen.getByLabelText('时间范围')
    expect(trigger).toHaveTextContent('全部时间')
    expect(trigger.textContent).not.toBe('all')
  })

  it('报告中心选中「今日」后回显「今日」', () => {
    reportHero('today')
    expect(screen.getByLabelText('时间范围')).toHaveTextContent('今日')
  })

  it('报告展示页默认显示「全部时间」，且顶部 Badge 不落英文 value', () => {
    showcaseHero('today')
    const trigger = screen.getByLabelText('时间范围')
    expect(trigger).toHaveTextContent('今日')
    expect(document.body.textContent).not.toContain('today')
  })
})

function advancedSearch(props: {
  deviceType?: string
  creator?: string
  timeRange?: ReportTimeRange | 'all'
}) {
  return render(
    <ReportAdvancedSearch
      deviceType={props.deviceType}
      creator={props.creator}
      timeRange={props.timeRange}
      onTimeRangeChange={vi.fn()}
      onChange={vi.fn()}
      onReset={vi.fn()}
    />
  )
}

describe('INT-2447 P3-1 残余 高级搜索三个 Select 文案', () => {
  it('展开后默认显示「全部 / 全部 / 全部时间」，不落英文 value', async () => {
    const user = userEvent.setup()
    const { container } = advancedSearch({})
    await user.click(screen.getByRole('button', { name: /高级搜索/ }))

    expect(screen.getByRole('combobox', { name: '设备类型' })).toHaveTextContent('全部')
    expect(screen.getByRole('combobox', { name: '创建者' })).toHaveTextContent('全部')
    expect(screen.getByRole('combobox', { name: '时间范围' })).toHaveTextContent('全部时间')

    const panel = container.textContent ?? ''
    expect(panel).not.toContain('smart_speaker')
    expect(panel).not.toContain('demo_admin')
    expect(panel).not.toMatch(/\ball\b/)
  })

  it('已选条件下回显中文 label（设备类型 / 创建者 / 时间范围）', async () => {
    const user = userEvent.setup()
    advancedSearch({
      deviceType: 'smart_speaker',
      creator: 'demo_admin',
      timeRange: 'today',
    })
    await user.click(screen.getByRole('button', { name: /高级搜索/ }))

    const device = screen.getByRole('combobox', { name: '设备类型' })
    const creator = screen.getByRole('combobox', { name: '创建者' })
    const range = screen.getByRole('combobox', { name: '时间范围' })
    expect(device).toHaveTextContent('智能音箱')
    expect(device.textContent).not.toBe('smart_speaker')
    expect(creator).toHaveTextContent('demo_admin')
    expect(range).toHaveTextContent('今日')
    expect(range.textContent).not.toBe('today')
  })

  it('切换时间范围「今日」→ 回调 today，受控回填后回显「今日」', async () => {
    const user = userEvent.setup()
    const onTimeRangeChange = vi.fn()
    const { rerender } = render(
      <ReportAdvancedSearch onTimeRangeChange={onTimeRangeChange} onChange={vi.fn()} onReset={vi.fn()} />
    )
    await user.click(screen.getByRole('button', { name: /高级搜索/ }))
    await user.click(screen.getByRole('combobox', { name: '时间范围' }))
    await user.click(await screen.findByRole('option', { name: '今日' }))
    expect(onTimeRangeChange).toHaveBeenCalledWith('today')

    rerender(
      <ReportAdvancedSearch
        timeRange='today'
        onTimeRangeChange={onTimeRangeChange}
        onChange={vi.fn()}
        onReset={vi.fn()}
      />
    )
    expect(screen.getByRole('combobox', { name: '时间范围' })).toHaveTextContent('今日')
  })
})

describe('INT-2447 P3-2 报告列表错误态', () => {
  it('表格视图：公共 ErrorState 文案（标题 + 重试），不再「请重试」', () => {
    errorTable()
    expect(screen.getByText('报告列表加载失败')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '请重试' })).toBeNull()
  })

  it('卡片视图：公共 ErrorState 文案（标题 + 重试），不再「请重试」', () => {
    errorCardGrid()
    expect(screen.getByText('报告列表加载失败')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '请重试' })).toBeNull()
  })

  it('错误态图标是 AlertTriangle（destructive），不是排序图标', () => {
    const { container } = errorTable()
    const icon = container.querySelector('[data-slot=empty-icon] svg')
    expect(icon).not.toBeNull()
    expect(icon?.getAttribute('class') ?? '').toContain('triangle-alert')
    expect(icon?.getAttribute('class') ?? '').toContain('text-destructive')
  })
})

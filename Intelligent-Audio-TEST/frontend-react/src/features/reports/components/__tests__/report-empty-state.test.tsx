/**
 * 报告中心空态判别 + 工具栏计数（INT-2350）：
 * - 空态按「是否处于筛选态」区分「未找到匹配报告」与「暂无报告」，不看计数
 *   （INT-2339 起计数随关键字收缩，用 totalCount === 0 判必错）；
 * - 回收站视图优先；
 * - 工具栏有筛选只留「已筛选 N」，无筛选只留「共 N」，同一计数不重复展示。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ReportCardGrid } from '@/features/reports/components/report-card-grid'
import { ReportFilterToolbar } from '@/features/reports/components/report-filter-toolbar'
import { ReportsTable } from '@/features/reports/components/reports-table'

const hasPermission = () => true

function table(props: { hasActiveFilters: boolean; trashMode?: boolean }) {
  return render(
    <ReportsTable
      items={[]}
      hasActiveFilters={props.hasActiveFilters}
      trashMode={props.trashMode ?? false}
      selectedIds={[]}
      onToggleRow={vi.fn()}
      onToggleAll={vi.fn()}
      hasPermission={hasPermission}
      onRowAction={vi.fn()}
      onRowClick={vi.fn()}
      onClearFilters={vi.fn()}
    />
  )
}

function cardGrid(props: { hasActiveFilters: boolean; trashMode?: boolean }) {
  return render(
    <ReportCardGrid
      items={[]}
      hasActiveFilters={props.hasActiveFilters}
      trashMode={props.trashMode ?? false}
      hasPermission={hasPermission}
      onRowAction={vi.fn()}
      onCardClick={vi.fn()}
      onClearFilters={vi.fn()}
    />
  )
}

function toolbar(hasActiveFilters: boolean) {
  return render(
    <ReportFilterToolbar
      filteredCount={7}
      totalCount={60}
      hasActiveFilters={hasActiveFilters}
      sortBy='created_at'
      sortOrder='desc'
      onSortChange={vi.fn()}
      viewMode='table'
      onViewModeChange={vi.fn()}
    />
  )
}

describe('ReportsTable 空态判别（INT-2350）', () => {
  it('筛选态无命中 → 「未找到匹配报告」+「试试其他关键字」+ 清除筛选', () => {
    table({ hasActiveFilters: true })
    expect(screen.getByText('未找到匹配报告')).toBeInTheDocument()
    expect(screen.getByText('试试其他关键字')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '清除全部筛选' })
    ).toBeInTheDocument()
    expect(screen.queryByText('暂无报告')).toBeNull()
  })

  it('无筛选且列表为空 → 「暂无报告」（库内真没有）', () => {
    table({ hasActiveFilters: false })
    expect(screen.getByText('暂无报告')).toBeInTheDocument()
    expect(
      screen.getByText('测试任务执行完成后生成的报告将在此展示')
    ).toBeInTheDocument()
    expect(screen.queryByText('未找到匹配报告')).toBeNull()
  })

  it('回收站视图优先 → 「回收站是空的」', () => {
    table({ hasActiveFilters: true, trashMode: true })
    expect(screen.getByText('回收站是空的')).toBeInTheDocument()
    expect(screen.queryByText('未找到匹配报告')).toBeNull()
  })
})

describe('ReportCardGrid 空态判别（INT-2350）', () => {
  it('筛选态无命中 → 「未找到匹配报告」', () => {
    cardGrid({ hasActiveFilters: true })
    expect(screen.getByText('未找到匹配报告')).toBeInTheDocument()
    expect(screen.getByText('试试其他关键字')).toBeInTheDocument()
  })

  it('无筛选且列表为空 → 「暂无报告」', () => {
    cardGrid({ hasActiveFilters: false })
    expect(screen.getByText('暂无报告')).toBeInTheDocument()
    expect(screen.queryByText('未找到匹配报告')).toBeNull()
  })

  it('回收站视图优先 → 「回收站是空的」', () => {
    cardGrid({ hasActiveFilters: true, trashMode: true })
    expect(screen.getByText('回收站是空的')).toBeInTheDocument()
  })
})

describe('ReportFilterToolbar 计数展示（INT-2350）', () => {
  it('无筛选 → 只展示「共 N 个报告」', () => {
    const { container } = toolbar(false)
    expect(container.textContent).toContain('共 60 个报告')
    expect(container.textContent).not.toContain('已筛选')
  })

  it('有筛选 → 只展示「已筛选 N 个报告」，不再重复「共 N」', () => {
    const { container } = toolbar(true)
    expect(container.textContent).toContain('已筛选 7 个报告')
    expect(container.textContent).not.toContain('共 60')
  })
})

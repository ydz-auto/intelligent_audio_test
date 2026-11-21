/**
 * 具体用例对比排序 Select 溢出策略回归（15_报告域.md §3.3.7/§3.5.10）：
 * - 「按评估维度」排序的 资源 / 评估维度 触发器带 `w-full min-w-0`（溢出策略契约），
 *   长资源名/长维度名在网格列内截断，不横向溢出到相邻列（实测复现：长资源名顶到右侧
 *   评估维度字段）；
 * - 两个下拉弹层带最小宽度（资源 `min-w-64` / 评估维度 `min-w-72`），长名称不被裁切。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { ReportCaseItem, ReportDetailData } from '@/domain/models/report'
import { SpecificCaseComparison } from '@/features/report-view/components/task-report-panel/specific-case-comparison'

const { LONG_RESOURCE, REPORT, CASE_HOOK, PERMISSIONS, ALGO_LABELS } = vi.hoisted(() => {
  const LONG_RESOURCE = '14-pura90-豆包-拒识回复行为数量（超长资源名防溢出回归）'
  const CASES: ReportCaseItem[] = [
    {
      id: 'case-reject',
      name: '测试用例-单轮拒识',
      category: '拒识',
      tags: [],
      metrics: { 'device-a': { '拒识成功数量': 1, '回复时拒识恢复行为数量': 1 } },
      results: [{ resource: LONG_RESOURCE, status: 'completed' }],
      audios: [],
    },
  ]
  const REPORT: ReportDetailData = {
    id: 1,
    name: '报告',
    type: 'task',
    task_name: '任务',
    status: 'published',
    created_at: '2026-11-21 10:00:00',
    summary: {
      total_cases: 1,
      completed_cases: 1,
      failed_cases: 0,
      resources: [LONG_RESOURCE],
      resource_headers: [],
      raw_data: [],
      metric_data: [],
      tag_metric_data: [],
      case_categories: [],
      all_case_tags: [],
      all_tags: [],
      all_metrics: [
        { name: '拒识成功数量', dimension_type: 'main' },
        { name: '回复时拒识恢复行为数量', dimension_type: 'sub', parent_dimension_name: '拒识成功数量' },
      ],
      case_type_stats: [],
      device_stats: [],
      api_stats: [],
      devices: [],
      apis: [],
      cases: CASES,
    },
  }
  const noop = () => undefined
  const CASE_HOOK = {
    // 排序方式切到「按评估维度」→ 渲染 资源 / 评估维度 两个 Select
    filters: { sortBy: 'metric' as const },
    setFilters: noop,
    applyFilters: noop,
    resetFilters: noop,
    items: CASES,
    isLoading: false,
    isFetching: false,
    isError: false,
    refetch: noop,
    total: CASES.length,
    pinnedIds: [],
    pinnedCases: [],
    togglePin: noop,
    expandedIds: [],
    toggleExpand: noop,
    clearExpanded: noop,
    downloadLogs: noop,
  }
  const PERMISSIONS = { hasPermission: () => false }
  const ALGO_LABELS: Record<string, string> = {}
  return { LONG_RESOURCE, CASES, REPORT, CASE_HOOK, PERMISSIONS, ALGO_LABELS }
})

vi.mock('@/application/report-view/use-report-cases', () => ({
  useReportCases: () => CASE_HOOK,
}))

vi.mock('@/application/hooks/use-permissions', () => ({
  usePermissions: () => PERMISSIONS,
}))

vi.mock('@/application/hooks/use-algorithm-options', () => ({
  useAlgorithmLabels: () => ALGO_LABELS,
}))

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecificCaseComparison report={REPORT} />
    </QueryClientProvider>
  )
}

describe('具体用例对比排序 Select 溢出策略（资源/评估维度）', () => {
  it('资源/评估维度触发器带 w-full min-w-0，长名不横向溢出', () => {
    renderPanel()
    // 排序卡四个 combobox：状态 / 排序方式 / 资源 / 评估维度
    const triggers = screen.getAllByRole('combobox')
    expect(triggers.length).toBe(4)
    const resourceTrigger = triggers[2]
    const metricTrigger = triggers[3]
    expect(resourceTrigger).toHaveClass('w-full', 'min-w-0')
    expect(metricTrigger).toHaveClass('w-full', 'min-w-0')
  })

  it('资源下拉弹层带最小宽度，长资源名不被裁切', async () => {
    const user = userEvent.setup()
    renderPanel()
    await user.click(screen.getAllByRole('combobox')[2])
    await screen.findByRole('option', { name: LONG_RESOURCE })
    expect(document.querySelector('[data-slot="select-content"]')).toHaveClass('min-w-64')
  })

  it('评估维度下拉弹层带最小宽度，长维度名不被裁切', async () => {
    const user = userEvent.setup()
    renderPanel()
    await user.click(screen.getAllByRole('combobox')[3])
    await screen.findByRole('option', { name: '回复时拒识恢复行为数量' })
    expect(document.querySelector('[data-slot="select-content"]')).toHaveClass('min-w-72')
  })
})

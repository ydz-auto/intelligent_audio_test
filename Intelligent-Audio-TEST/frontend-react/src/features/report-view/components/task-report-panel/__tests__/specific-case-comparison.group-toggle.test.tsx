/**
 * 具体用例对比分组头展开/收起回归（15_报告域.md §3.3.7 组织层语义）：
 * 分组视图 / 标签视图的组头在页面态必须可点击展开/收起组内用例（与导出态
 * `data-export-group-toggle` 的产物行为对齐，INT-2434 三轮「组头原来是死文字」的页面侧缺口）；
 * 各组折叠状态相互独立（按层级 + 叶表上下文隔离）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ReportCaseItem, ReportDetailData } from '@/domain/models/report'
import { SpecificCaseComparison } from '@/features/report-view/components/task-report-panel/specific-case-comparison'

const { REPORT, CASE_HOOK, PERMISSIONS, ALGO_LABELS } = vi.hoisted(() => {
  const CASES: ReportCaseItem[] = [
    {
      id: 'case-reject',
      name: '测试用例-单轮拒识',
      category: '拒识',
      tags: [],
      metrics: {},
      results: [{ resource: 'device-a', status: 'completed' }],
      audios: [],
    },
    {
      id: 'case-normal',
      name: '测试用例-正常应答',
      category: '正常',
      tags: [],
      metrics: {},
      results: [{ resource: 'device-a', status: 'completed' }],
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
      total_cases: 2,
      completed_cases: 2,
      failed_cases: 0,
      resources: ['device-a'],
      resource_headers: [],
      raw_data: [],
      metric_data: [],
      tag_metric_data: [],
      case_categories: [],
      all_case_tags: [],
      all_tags: [],
      all_metrics: [],
      case_type_stats: [],
      device_stats: [],
      api_stats: [],
      devices: [],
      apis: [],
      cases: CASES,
    },
  }
  /**
   * hooks 返回值必须跨渲染稳定（组件内 useEffect 依赖回调引用，每次渲染新建
   * vi.fn() 会反复触发 effect → 死循环）。全部在 hoisted 作用域创建一次。
   */
  const noop = () => undefined
  const CASE_HOOK = {
    filters: {},
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
  return { CASES, REPORT, CASE_HOOK, PERMISSIONS, ALGO_LABELS }
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

describe('具体用例对比分组头展开/收起', () => {
  it('分组头默认展开组内用例，点击收起后组内用例消失，再次点击恢复', () => {
    renderPanel()
    const header = screen.getByRole('button', { name: '展开或收起分组 拒识' })

    // 默认展开：组头 aria-expanded=true，组内用例可见
    expect(header).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('测试用例-单轮拒识')).toBeInTheDocument()

    // 点击收起：组内用例不再渲染
    fireEvent.click(header)
    expect(header).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('测试用例-单轮拒识')).not.toBeInTheDocument()

    // 再次点击展开：组内用例恢复
    fireEvent.click(header)
    expect(header).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('测试用例-单轮拒识')).toBeInTheDocument()
  })

  it('各组折叠状态相互独立，收起一组不影响其他分组', () => {
    renderPanel()
    const rejectHeader = screen.getByRole('button', { name: '展开或收起分组 拒识' })

    fireEvent.click(rejectHeader)
    expect(screen.queryByText('测试用例-单轮拒识')).not.toBeInTheDocument()
    // 另一分组的组内用例保持可见
    expect(screen.getByText('测试用例-正常应答')).toBeInTheDocument()
    const normalHeader = screen.getByRole('button', { name: '展开或收起分组 正常' })
    expect(normalHeader).toHaveAttribute('aria-expanded', 'true')
  })
})

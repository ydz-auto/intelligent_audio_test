/**
 * 按用例标签对比-标签筛选搜索（15_报告域.md §3.3.6）：
 * 搜索框按标签名过滤（无命中的分类整组隐藏）；分类名整体命中保留整组；
 * 无任何命中展示「无匹配标签」；已选标签在搜索过滤下保持勾选与计数。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ReportDetailData } from '@/domain/models/report'
import { CaseTagComparison } from '@/features/report-view/components/task-report-panel/case-tag-comparison'

// 矩阵卡片引 VChart 在 jsdom 下无法解析（@visactor/vchart esm 子模块），
// 搜索行为测试不涉及图表展示，整模块替换为空实现即可（同库其它 report-view 测试口径）。
vi.mock('@/components/common/report-chart', () => ({
  ReportChart: () => null,
}))

function makeReport(): ReportDetailData {
  return {
    id: 1,
    name: '报告',
    type: 'task',
    task_name: '任务',
    status: 'published',
    created_at: '2026-11-21 10:00:00',
    summary: {
      total_cases: 4,
      completed_cases: 4,
      failed_cases: 0,
      resources: ['device-a'],
      resource_headers: [],
      raw_data: [],
      metric_data: [],
      tag_metric_data: [
        {
          resource: 'device-a',
          tags: [
            { tag_id: '1', tag_name: '单轮拒识', category_id: '1', category_name: '其他', metrics: [] },
            { tag_id: '2', tag_name: '多轮对话', category_id: '1', category_name: '其他', metrics: [] },
            { tag_id: '3', tag_name: '唤醒词', category_id: '2', category_name: '唤醒', metrics: [] },
            { tag_id: '4', tag_name: '断句错误', category_id: '2', category_name: '唤醒', metrics: [] },
          ],
        },
      ],
      case_categories: [],
      all_case_tags: [],
      all_metrics: [{ name: '准确率' }],
      case_type_stats: [],
      device_stats: [],
      api_stats: [],
      devices: [],
      apis: [],
      cases: [],
    },
  }
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <CaseTagComparison report={makeReport()} />
    </QueryClientProvider>
  )
}

describe('按用例标签对比-标签筛选搜索', () => {
  it('输入标签名关键词后仅显示命中标签，无命中的分类整组隐藏', () => {
    renderPanel()
    // 初始：两个分类组头、四枚标签全部展示（分类组头是 <p>，矩阵表头是 <td>，用 selector 区分）
    expect(screen.getByText('其他', { selector: 'p' })).toBeInTheDocument()
    expect(screen.getByText('唤醒', { selector: 'p' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: '单轮拒识' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: '多轮对话' })).toBeInTheDocument()

    fireEvent.change(screen.getByRole('textbox', { name: '搜索用例标签' }), {
      target: { value: '拒识' },
    })

    expect(screen.getByRole('checkbox', { name: '单轮拒识' })).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: '多轮对话' })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: '唤醒词' })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: '断句错误' })).not.toBeInTheDocument()
    // 仅剩「其他」分类组头，无命中的「唤醒」分类整组隐藏
    expect(screen.queryByText('唤醒', { selector: 'p' })).not.toBeInTheDocument()
  })

  it('分类名整体命中时保留该分类全部标签', () => {
    renderPanel()
    fireEvent.change(screen.getByRole('textbox', { name: '搜索用例标签' }), {
      target: { value: '唤醒' },
    })

    expect(screen.getByRole('checkbox', { name: '唤醒词' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: '断句错误' })).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: '单轮拒识' })).not.toBeInTheDocument()
  })

  it('无任何命中展示「无匹配标签」空态', () => {
    renderPanel()
    fireEvent.change(screen.getByRole('textbox', { name: '搜索用例标签' }), {
      target: { value: '不存在的标签' },
    })

    expect(screen.getByText('无匹配标签')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: '单轮拒识' })).not.toBeInTheDocument()
  })

  it('清空关键词后恢复全量标签列表', () => {
    renderPanel()
    const searchBox = screen.getByRole('textbox', { name: '搜索用例标签' })
    fireEvent.change(searchBox, { target: { value: '拒识' } })
    expect(screen.queryByRole('checkbox', { name: '多轮对话' })).not.toBeInTheDocument()

    fireEvent.change(searchBox, { target: { value: '' } })
    expect(screen.getByRole('checkbox', { name: '多轮对话' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: '唤醒词' })).toBeInTheDocument()
  })

  it('已选标签在搜索过滤下保持勾选与已选计数', () => {
    renderPanel()
    // 先勾选「多轮对话」
    fireEvent.click(screen.getByRole('checkbox', { name: '多轮对话' }))
    expect(screen.getByRole('checkbox', { name: '多轮对话' })).toBeChecked()
    expect(screen.getByText('已选 1')).toBeInTheDocument()

    // 搜索后该标签被过滤隐藏，但已选计数不变
    fireEvent.change(screen.getByRole('textbox', { name: '搜索用例标签' }), {
      target: { value: '拒识' },
    })
    expect(screen.queryByRole('checkbox', { name: '多轮对话' })).not.toBeInTheDocument()
    expect(screen.getByText('已选 1')).toBeInTheDocument()

    // 命中标签仍可勾选，计数累加
    fireEvent.click(screen.getByRole('checkbox', { name: '单轮拒识' }))
    expect(screen.getByText('已选 2')).toBeInTheDocument()

    // 清空关键词后「多轮对话」仍处于勾选态
    fireEvent.change(screen.getByRole('textbox', { name: '搜索用例标签' }), {
      target: { value: '' },
    })
    expect(screen.getByRole('checkbox', { name: '多轮对话' })).toBeChecked()
    expect(screen.getByText('已选 2')).toBeInTheDocument()
  })
})

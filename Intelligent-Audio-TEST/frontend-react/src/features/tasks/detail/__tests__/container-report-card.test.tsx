/**
 * 容器详情「报告」卡组件测试（18_挑选合并功能交互重设计.md §5.5.2 ④ / §5.5.6，INT-1717）。
 * 覆盖：无报告 → 空态引导手动生成 + 生成后回显；已有报告 → 名称 + 查看报告；
 * 报告列表加载失败 → 错误态 + 重试（不白屏、不裸 id）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchReportList: vi.fn(),
  generateTaskReport: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}))

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, to }: { children: ReactNode; to: string }) => <a href={to}>{children}</a>,
}))

vi.mock('@/application/hooks/use-permissions', () => ({
  usePermissions: () => ({ hasPermission: () => true }),
}))

vi.mock('@/infrastructure/api/reports-api', () => ({
  fetchReportList: (...args: unknown[]) => mocks.fetchReportList(...args),
  generateTaskReport: (...args: unknown[]) => mocks.generateTaskReport(...args),
}))

vi.mock('sonner', () => ({
  toast: { success: mocks.toastSuccess, error: mocks.toastError },
}))

import { ContainerReportCard } from '@/features/tasks/detail/container-report-card'

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ContainerReportCard taskId={611} />
    </QueryClientProvider>
  )
}

function reportItem(id: number) {
  return {
    id,
    name: `接线测试_容器报告_${id}`,
    type: 'task',
    task_id: 611,
    task_name: '接线测试_容器',
    summary: { total_cases: 1, completed_cases: 1, failed_cases: 0, pass_rate: 1 },
    status: 'draft',
    created_at: '2026-10-25 10:00',
  }
}

describe('ContainerReportCard（§5.5.6 无报告态）', () => {
  beforeEach(() => {
    mocks.fetchReportList.mockReset()
    mocks.generateTaskReport.mockReset()
    mocks.toastSuccess.mockReset()
  })

  it('无报告 → 空态文案 + 生成报告按钮', async () => {
    mocks.fetchReportList.mockResolvedValue({ items: [], total: 0, page: 1, per_page: 1, pages: 0 })
    renderCard()

    expect(await screen.findByText('该合并任务暂无报告')).toBeInTheDocument()
    // 卡头一行 + 空态说明各一处（同口径文案）
    expect(screen.getAllByText('合并任务无执行过程，报告需手动生成').length).toBeGreaterThan(0)
    expect(mocks.fetchReportList).toHaveBeenCalledWith(expect.objectContaining({ task_id: 611 }))
  })

  it('生成报告 → 调既有 generate-task + toast + 回显报告', async () => {
    mocks.fetchReportList.mockResolvedValue({ items: [], total: 0, page: 1, per_page: 1, pages: 0 })
    mocks.generateTaskReport.mockResolvedValue({ report_id: 88 })
    renderCard()

    fireEvent.click(await screen.findByRole('button', { name: '生成报告' }))

    await waitFor(() =>
      expect(mocks.generateTaskReport).toHaveBeenCalledWith({ task_id: 611 })
    )
    await waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalledWith('报告生成成功'))
    // 后端异步生成：先进入「报告生成中…」，不谎报「暂无报告」
    expect(await screen.findByText('报告生成中…')).toBeInTheDocument()
  })

  it('已有报告 → 名称 + 查看报告入口', async () => {
    mocks.fetchReportList.mockResolvedValue({
      items: [reportItem(88)],
      total: 1,
      page: 1,
      per_page: 1,
      pages: 1,
    })
    renderCard()

    expect(await screen.findByText('接线测试_容器报告_88')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '查看报告' })).toBeInTheDocument()
    expect(screen.queryByText('该合并任务暂无报告')).not.toBeInTheDocument()
  })

  it('报告列表加载失败 → 错误态 + 重试（不误报「暂无报告」）', async () => {
    mocks.fetchReportList.mockRejectedValue(new Error('boom'))
    renderCard()

    expect(await screen.findByText('报告加载失败')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
  })
})

/**
 * 容器详情「报告」卡组件测试（18_挑选合并功能交互重设计.md §5.5.2 ④ / §5.5.6，INT-1717）。
 * 覆盖：无报告 → 空态引导手动生成 + 生成后回显；已有报告 → 名称 + 查看报告；
 * 报告列表加载失败 → 错误态 + 重试（不白屏、不裸 id）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReportListItem } from '@/domain/models/report'

const mocks = vi.hoisted(() => ({
  fetchLatestReportByTask: vi.fn(),
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
  fetchLatestReportByTask: (...args: unknown[]) => mocks.fetchLatestReportByTask(...args),
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

/** 组件只读 id / name / status（报告域其余字段与本卡无关，最小夹具即可） */
function reportItem(id: number): ReportListItem {
  return { id, name: `接线测试_容器报告_${id}`, status: 'draft' } as ReportListItem
}

describe('ContainerReportCard（§5.5.6 无报告态）', () => {
  beforeEach(() => {
    mocks.fetchLatestReportByTask.mockReset()
    mocks.generateTaskReport.mockReset()
    mocks.toastSuccess.mockReset()
  })

  it('无报告 → 空态文案 + 生成报告按钮', async () => {
    mocks.fetchLatestReportByTask.mockResolvedValue(null)
    renderCard()

    expect(await screen.findByText('该合并任务暂无报告')).toBeInTheDocument()
    // 卡头一行 + 空态说明各一处（同口径文案）
    expect(screen.getAllByText('合并任务无执行过程，报告需手动生成').length).toBeGreaterThan(0)
    expect(mocks.fetchLatestReportByTask).toHaveBeenCalledWith(611)
  })

  it('生成报告 → 调既有 generate-task + toast + 回显报告', async () => {
    mocks.fetchLatestReportByTask.mockResolvedValue(null)
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
    mocks.fetchLatestReportByTask.mockResolvedValue(reportItem(88))
    renderCard()

    expect(await screen.findByText('接线测试_容器报告_88')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '查看报告' })).toBeInTheDocument()
    expect(screen.queryByText('该合并任务暂无报告')).not.toBeInTheDocument()
  })

  it('报告列表加载失败 → 错误态 + 重试（不误报「暂无报告」）', async () => {
    mocks.fetchLatestReportByTask.mockRejectedValue(new Error('boom'))
    renderCard()

    expect(await screen.findByText('报告加载失败')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
  })
})

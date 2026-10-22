/**
 * 任务复核历史抽屉测试（INT-795，19 规范 §3.4）。
 * 覆盖：历史条目渲染（时间/操作人/字段徽章/改判原值→新值/备注）、空态「暂无复核记录」、
 * 按 resultId 过滤（单条复核弹窗「查看复核历史」入口）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ReviewHistoryItem } from '@/domain/models/review'

import { ReviewHistoryDrawer } from '../review-history-drawer'

const fetchReviewHistoryMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/reviewApi', () => ({
  submitReview: vi.fn(),
  fetchReviewHistory: fetchReviewHistoryMock,
  fetchReviewCount: vi.fn(),
  fetchCaseResults: vi.fn(),
  requestAiReview: vi.fn(),
  fetchAiReviewHistory: vi.fn(),
  adoptAiReview: vi.fn(),
  rejectAiReview: vi.fn(),
}))

const historyItems: ReviewHistoryItem[] = [
  {
    id: 1,
    resultId: 5400,
    taskId: 417,
    testCaseId: 'case-1',
    fieldName: 'execution_status',
    oldValue: 'failed',
    newValue: 'completed',
    comment: '人工确认通过',
    createdByUserId: 5,
    createdAt: '2026-10-18T09:20:00.000',
  },
  {
    id: 2,
    resultId: 5400,
    taskId: 417,
    testCaseId: 'case-1',
    fieldName: 'evaluation_status',
    oldValue: 'failed',
    newValue: 'completed',
    comment: '评估复核通过',
    createdByUserId: null,
    createdAt: '2026-10-18T09:21:00.000',
  },
]

function renderDrawer(props?: Partial<Parameters<typeof ReviewHistoryDrawer>[0]>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ReviewHistoryDrawer
        open
        onOpenChange={vi.fn()}
        taskId={417}
        taskName='任务A'
        caseNameMap={{ 'case-1': '用例一' }}
        {...props}
      />
    </QueryClientProvider>
  )
}

describe('ReviewHistoryDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('历史条目渲染：用例名 + 字段徽章 + 改判原值→新值 + 备注 + 操作人', async () => {
    fetchReviewHistoryMock.mockResolvedValue(historyItems)
    renderDrawer()
    expect(await screen.findByText('复核历史 — 任务A')).toBeInTheDocument()
    expect(await screen.findByText('共 2 条')).toBeInTheDocument()
    // 用例名在每条历史行用例徽章出现 → 复数断言
    expect(screen.getAllByText('用例一').length).toBe(2)
    expect(screen.getByText('执行状态')).toBeInTheDocument()
    expect(screen.getByText('评估状态')).toBeInTheDocument()
    // 改判：原值 failed（两条行均改判自 failed）+ destructive 箭头「→」
    expect(screen.getAllByText('failed').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('→').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('操作人 用户 #5')).toBeInTheDocument()
    expect(screen.getByText('操作人 —')).toBeInTheDocument()
    expect(screen.getByText('人工确认通过')).toBeInTheDocument()
  })

  it('空态：无记录时显示「暂无复核记录」', async () => {
    fetchReviewHistoryMock.mockResolvedValue([])
    renderDrawer()
    expect(await screen.findByText('暂无复核记录')).toBeInTheDocument()
    expect(screen.queryByText('共 0 条')).toBeInTheDocument()
  })

  it('按 resultId 过滤：单条复核弹窗「查看复核历史」入口只显该结果留痕', async () => {
    fetchReviewHistoryMock.mockResolvedValue([
      ...historyItems,
      { ...historyItems[0], id: 3, resultId: 9999, testCaseId: 'case-other' },
    ])
    renderDrawer({ resultId: 5400 })
    await waitFor(() => expect(screen.getByText('共 2 条')).toBeInTheDocument())
    expect(screen.queryByText('case-other')).not.toBeInTheDocument()
  })

  it('抽屉未打开时不发复核历史请求（enabled 门控，防 taskId=0 无效请求）', () => {
    renderDrawer({ open: false })
    expect(fetchReviewHistoryMock).not.toHaveBeenCalled()
  })

  it('taskId<=0 时即使打开也不发复核历史请求', () => {
    renderDrawer({ taskId: 0 })
    expect(fetchReviewHistoryMock).not.toHaveBeenCalled()
  })
})

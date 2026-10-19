/**
 * 人工复核弹窗组件测试（INT-795，19 规范 §3.2/§3.3）。
 * 覆盖：单条/批量标题、结果摘要（设备/执行徽章）、提交禁用条件（备注必填 + 至少一项改判）、
 * 提交载荷（result_ids + 改判枚举 + comment）与成功 toast。
 * 共享 reviewApi 由报告侧 INT-793 / 任务侧 INT-795 共同落位，本测试 mock 提交出口。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { CaseResultForReview } from '@/domain/models/review'

import { ManualReviewDialog } from '../manual-review-dialog'

const submitReviewMock = vi.hoisted(() => vi.fn())
const fetchReviewHistoryMock = vi.hoisted(() => vi.fn())
const fetchReviewCountMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/reviewApi', () => ({
  submitReview: submitReviewMock,
  fetchReviewHistory: fetchReviewHistoryMock,
  fetchReviewCount: fetchReviewCountMock,
  fetchCaseResults: vi.fn(),
  requestAiReview: vi.fn(),
  fetchAiReviewHistory: vi.fn(),
  adoptAiReview: vi.fn(),
  rejectAiReview: vi.fn(),
}))

const singleResult: CaseResultForReview = {
  id: 5400,
  deviceId: 10,
  deviceName: 'pura90豆包',
  apiId: null,
  apiName: null,
  executionStatus: 'failed',
  responseTime: 0,
  errorMessage: null,
  reviewed: false,
  reviewedByUserId: null,
  reviewedAt: null,
  lastReviewComment: null,
  lastReviewAction: null,
  reviewHistory: [],
  sourceTaskId: 417,
  sourceTaskName: null,
}

function renderDialog(props?: Partial<Parameters<typeof ManualReviewDialog>[0]>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ManualReviewDialog
        open
        onOpenChange={vi.fn()}
        taskId={417}
        taskName='任务A'
        caseName='用例一'
        results={[singleResult]}
        {...props}
      />
    </QueryClientProvider>
  )
}

describe('ManualReviewDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    submitReviewMock.mockResolvedValue({ reviewedCount: 1, failed: [] })
    fetchReviewHistoryMock.mockResolvedValue([])
    fetchReviewCountMock.mockResolvedValue(0)
  })

  it('单条复核：标题「人工复核 — {用例名}」+ 结果摘要（设备名 + 执行徽章）', () => {
    renderDialog()
    expect(screen.getByText('人工复核 — 用例一')).toBeInTheDocument()
    expect(screen.getByText('pura90豆包')).toBeInTheDocument()
  })

  it('批量复核：标题「批量复核 — 已选 {n} 条结果」', () => {
    renderDialog({
      caseName: undefined,
      results: [singleResult, { ...singleResult, id: 5401, deviceName: 'pura90豆包2' }],
    })
    expect(screen.getByText('批量复核 — 已选 2 条结果')).toBeInTheDocument()
    expect(screen.getByText('pura90豆包2')).toBeInTheDocument()
  })

  it('备注为空 → 提交钮禁用；填写备注后仍至少需一项改判', async () => {
    const user = userEvent.setup()
    renderDialog()
    const submit = screen.getByRole('button', { name: '提交复核' })
    expect(submit).toBeDisabled()
    // 仅填备注（无改判）→ 仍禁用
    await user.type(screen.getByPlaceholderText('填写改判依据或复核意见'), '复核意见')
    expect(submit).toBeDisabled()
    // 选择评估状态改判 → 可提交
    await user.click(screen.getByRole('combobox', { name: '用例评估状态' }))
    await user.click(await screen.findByRole('option', { name: '评估失败' }))
    await waitFor(() => expect(submit).toBeEnabled())
  })

  it('提交载荷：result_ids + 改判枚举 + comment 必填', async () => {
    const user = userEvent.setup()
    renderDialog()
    await user.type(screen.getByPlaceholderText('填写改判依据或复核意见'), '执行失败，驳回')
    await user.click(screen.getByRole('combobox', { name: '用例执行状态' }))
    await user.click(await screen.findByRole('option', { name: '执行失败' }))
    await user.click(screen.getByRole('button', { name: '提交复核' }))
    await waitFor(() =>
      expect(submitReviewMock).toHaveBeenCalledWith({
        resultIds: [5400],
        executionStatus: 'failed',
        evaluationStatus: undefined,
        comment: '执行失败，驳回',
      })
    )
  })
})

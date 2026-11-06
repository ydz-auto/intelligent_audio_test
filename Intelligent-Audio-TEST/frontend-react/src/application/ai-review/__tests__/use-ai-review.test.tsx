/**
 * useAiReview 单测（INT-1545）：容器任务下页面 taskId ≠ 记录归属任务——
 * 发起响应 item.task_id 指向结果所属源任务，历史轮询须切到该归属任务推进状态机，
 * 否则永远查不到记录、卡在「执行中」。普通任务（归属 = 页面任务）保持原行为。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AiReviewRecord } from '@/domain/models/review'

import { useAiReview } from '../use-ai-review'

const requestAiReviewMock = vi.hoisted(() => vi.fn())
const fetchAiReviewHistoryMock = vi.hoisted(() => vi.fn())
const adoptAiReviewMock = vi.hoisted(() => vi.fn())
const rejectAiReviewMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/reviewApi', () => ({
  submitReview: vi.fn(),
  fetchReviewHistory: vi.fn(),
  fetchReviewCount: vi.fn(),
  fetchCaseResults: vi.fn(),
  requestAiReview: requestAiReviewMock,
  fetchAiReviewHistory: fetchAiReviewHistoryMock,
  adoptAiReview: adoptAiReviewMock,
  rejectAiReview: rejectAiReviewMock,
}))

function record(overrides: Partial<AiReviewRecord> = {}): AiReviewRecord {
  return {
    id: 10,
    resultId: 5622,
    taskId: 417,
    testCaseId: 'case-1',
    dimensionId: 121,
    status: 'completed',
    verdict: 'passed',
    confidence: 0.9,
    reasoning: '测试理由',
    adopted: false,
    adoptedByUserId: null,
    adoptedAt: null,
    rejected: false,
    rejectedByUserId: null,
    rejectedAt: null,
    createdAt: '2026-10-23T00:00:00Z',
    updatedAt: null,
    ...overrides,
  }
}

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

describe('useAiReview（INT-1545：轮询键按记录归属任务）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('容器任务：发起响应 item.task_id=418 → 历史按 418 查并推进到 completed', async () => {
    requestAiReviewMock.mockResolvedValue(record({ status: 'running', taskId: 418 }))
    fetchAiReviewHistoryMock.mockImplementation(async (historyTaskId: number) =>
      historyTaskId === 418 ? [record({ id: 10, taskId: 418 })] : []
    )
    const { result } = renderHook(() => useAiReview(527, 'case-1'), {
      wrapper: createWrapper(),
    })
    await act(async () => {
      await result.current.save({ resultIds: [5622], dimensionIds: [121] })
    })
    await waitFor(() => {
      expect(result.current.phase).toBe('completed')
    })
    expect(fetchAiReviewHistoryMock).toHaveBeenCalledWith(418)
    expect(result.current.record?.id).toBe(10)
  })

  it('普通任务：发起响应 item.task_id=页面 taskId=417 → 仍按 417 推进（不退化）', async () => {
    requestAiReviewMock.mockResolvedValue(record({ status: 'completed', taskId: 417 }))
    fetchAiReviewHistoryMock.mockResolvedValue([record({ id: 10, taskId: 417 })])
    const { result } = renderHook(() => useAiReview(417, 'case-1'), {
      wrapper: createWrapper(),
    })
    await act(async () => {
      await result.current.save({ resultIds: [5622] })
    })
    expect(result.current.phase).toBe('completed')
    expect(requestAiReviewMock).toHaveBeenCalledWith(417, 'case-1', {
      resultIds: [5622],
    })
  })
})

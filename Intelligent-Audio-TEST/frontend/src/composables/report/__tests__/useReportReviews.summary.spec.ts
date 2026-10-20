/**
 * INT-1025 回归 —— 报告侧人工复核弹窗摘要行透传用例名/设备名。
 *
 * 缺陷：useReportReviews.openManualReview 构造 resultMetas 只带
 * resultId / executionStatus / evaluationStatus，未传 caseName（caseItem.name）
 * 与 deviceName/apiName → ResultReviewModal 摘要行显示「用例」/「—」。
 * 修复：摘要行完整透传（对齐任务详情侧 TestExecutionComponent 契约）——
 * caseName=用例名，result 行带 deviceName/apiName/reviewed；
 * AI 采纳入口（adoptAiReview）同源补全。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mocks = vi.hoisted(() => ({
  openModal: vi.fn(),
  getCaseResults: vi.fn(),
  getReviewCount: vi.fn(),
  getReviewHistory: vi.fn(),
  submitReview: vi.fn(),
  submitAiReview: vi.fn(),
  adoptAiReview: vi.fn(),
  rejectAiReview: vi.fn(),
}))

vi.mock('@/composables/modal/useModal', () => ({
  MODAL_TYPES: { RESULT_REVIEW: 'resultReview' },
  useModalControl: () => ({ open: mocks.openModal }),
}))

vi.mock('@/infrastructure/api/tasksApi', () => ({
  tasksApi: { getCaseResults: mocks.getCaseResults },
}))

vi.mock('@/infrastructure/api/reviewApi', () => ({
  reviewApi: {
    getReviewCount: mocks.getReviewCount,
    getReviewHistory: mocks.getReviewHistory,
    submitReview: mocks.submitReview,
    submitAiReview: mocks.submitAiReview,
    adoptAiReview: mocks.adoptAiReview,
    rejectAiReview: mocks.rejectAiReview,
  },
}))

import { useReportReviews } from '../useReportReviews'

/** 构造报告复核编排（report.taskId 落来源任务，供 openManualReview/adoptAiReview 溯源） */
function buildReviews(reportData: any = { taskId: 1257 }) {
  return useReportReviews(() => reportData)
}

describe('INT-1025：报告侧人工复核弹窗摘要行', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getReviewCount.mockResolvedValue(0)
    mocks.getReviewHistory.mockResolvedValue([])
    mocks.submitReview.mockResolvedValue(undefined)
    mocks.openModal.mockResolvedValue({ executionStatus: 'completed', evaluationStatus: 'completed', comment: '复核通过' })
  })

  it('openManualReview 透传 caseName + deviceName/apiName/reviewed（单条摘要行）', async () => {
    // tasksApi.getCaseResults 返回适配器输出的 camelCase ReadModel（CaseResults）
    mocks.getCaseResults.mockResolvedValue({
      taskId: '1257',
      caseId: 'INT314SMOKE_70ed974e',
      caseName: 'INT314SMOKE_70ed974e_API用例',
      results: [
        {
          id: 501,
          deviceId: 7,
          deviceName: '设备A',
          executionStatus: 'completed',
          evaluationStatus: 'completed',
          reviewed: true,
          reviewHistory: [{ id: 1, resultId: 501 }],
        },
      ],
    })

    const reviews = buildReviews()
    await reviews.loadReportReviews({ taskId: 1257 })
    await reviews.openManualReview({ id: 'INT314SMOKE_70ed974e', name: 'INT314SMOKE_70ed974e_API用例' })

    expect(mocks.openModal).toHaveBeenCalledTimes(1)
    const [, modalConfig] = mocks.openModal.mock.calls[0]
    expect(modalConfig.caseName).toBe('INT314SMOKE_70ed974e_API用例')
    expect(modalConfig.results).toEqual([
      {
        resultId: 501,
        executionStatus: 'completed',
        evaluationStatus: 'completed',
        deviceName: '设备A',
        apiName: undefined,
        reviewed: true,
      },
    ])
  })

  it('openManualReview 结果行无 caseName 时回退 caseItem.name', async () => {
    mocks.getCaseResults.mockResolvedValue({
      taskId: '1257',
      results: [{ id: 502, apiName: 'voice-llm API', executionStatus: 'failed' }],
    })

    const reviews = buildReviews()
    await reviews.loadReportReviews({ taskId: 1257 })
    await reviews.openManualReview({ id: 'C2', name: 'API用例B' })

    const [, modalConfig] = mocks.openModal.mock.calls[0]
    expect(modalConfig.caseName).toBe('API用例B')
    expect(modalConfig.results[0]).toMatchObject({ resultId: 502, apiName: 'voice-llm API' })
  })

  it('openManualReview 提交后经 reviewApi.submitReview 落留痕（载荷对齐人工复核契约）', async () => {
    mocks.getCaseResults.mockResolvedValue({
      results: [{ id: 503, deviceName: '设备C', executionStatus: 'completed' }],
    })

    const reviews = buildReviews()
    await reviews.loadReportReviews({ taskId: 1257 })
    await reviews.openManualReview({ id: 'C3', name: '用例C' })

    expect(mocks.submitReview).toHaveBeenCalledWith({
      resultIds: [503],
      executionStatus: 'completed',
      evaluationStatus: 'completed',
      comment: '复核通过',
    })
  })

  it('adoptAiReview（AI 采纳）弹窗摘要行同源透传 caseName + 设备名', async () => {
    mocks.getCaseResults.mockResolvedValue({
      taskId: '1257',
      caseName: 'INT314SMOKE_70ed974e_API用例',
      results: [{ id: 601, deviceId: 8, deviceName: '设备B', executionStatus: 'failed' }],
    })
    mocks.submitAiReview.mockResolvedValue({
      id: 9001,
      resultId: 601,
      taskId: 1257,
      verdict: 'passed',
      reasoning: 'AI 判定通过',
      adopted: false,
      rejected: false,
      createdAt: '2026-10-20T09:00:00',
      status: 'completed',
    })
    mocks.adoptAiReview.mockResolvedValue({})

    const reviews = buildReviews()
    await reviews.loadReportReviews({ taskId: 1257 })
    const caseItem = { id: 'INT314SMOKE_70ed974e', name: 'INT314SMOKE_70ed974e_API用例' }
    await reviews.initiateAiReview(caseItem)
    await reviews.adoptAiReview(caseItem)

    const [, modalConfig] = mocks.openModal.mock.calls[0]
    expect(modalConfig.caseName).toBe('INT314SMOKE_70ed974e_API用例')
    expect(modalConfig.results[0]).toMatchObject({
      resultId: 601,
      deviceName: '设备B',
      executionStatus: 'failed',
      evaluationStatus: 'completed', // verdict=passed → 预填 completed
    })
    expect(mocks.adoptAiReview).toHaveBeenCalledWith(9001, expect.objectContaining({
      executionStatus: 'completed',
      evaluationStatus: 'completed',
      comment: '复核通过',
    }))
  })
})

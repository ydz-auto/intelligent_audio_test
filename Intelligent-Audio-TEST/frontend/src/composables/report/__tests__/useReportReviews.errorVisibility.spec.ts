/**
 * INT-1042：报告侧人工审核错误路径不再静默 —— reviewsError / loadingReviews 绑定渲染 +
 * 交互失败走 toast（useNotification）。锁定契约：
 * 1. 复核历史加载失败 → reviewsError 置友好文案（原始 RPC 文本不外露）；
 * 2. openManualReview 无结果行 → reviewsError + notification.error；
 * 3. openManualReview 提交失败 → reviewsError + notification.error（toUserErrorMessage 收敛）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const notifications = vi.hoisted(() => ({ error: vi.fn(), show: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() }))
const reviewApiMock = vi.hoisted(() => ({
  getReviewCount: vi.fn(),
  getReviewHistory: vi.fn(),
  submitReview: vi.fn(),
  submitAiReview: vi.fn(),
  adoptAiReview: vi.fn(),
  rejectAiReview: vi.fn(),
}))
const tasksApiMock = vi.hoisted(() => ({ getCaseResults: vi.fn() }))
const modalOpenMock = vi.hoisted(() => vi.fn())

vi.mock('@/composables/modal/useNotification', () => ({ useNotification: () => notifications }))
vi.mock('@/infrastructure/api/reviewApi', () => ({ reviewApi: reviewApiMock }))
vi.mock('@/infrastructure/api/tasksApi', () => ({ tasksApi: tasksApiMock }))
vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({ open: modalOpenMock }),
  MODAL_TYPES: { RESULT_REVIEW: 'RESULT_REVIEW' },
}))

import { useReportReviews } from '../useReportReviews'

beforeEach(() => {
  vi.clearAllMocks()
  reviewApiMock.getReviewCount.mockResolvedValue(0)
  reviewApiMock.getReviewHistory.mockResolvedValue([])
})

const makeReport = (taskId = 1) => ({ id: 9, taskId, summaries: [{ metadata: {} }] })

describe('useReportReviews 错误可见性（INT-1042）', () => {
  it('复核历史加载失败：reviewsError 置友好文案，不直出原始 RPC 文本', async () => {
    reviewApiMock.getReviewHistory.mockRejectedValue(
      new Error('<_InactiveRpcError of RPC that terminated with: status=StatusCode.UNAVAILABLE details="failed to connect...">'),
    )
    const r = useReportReviews(() => makeReport())

    await r.loadReportReviews(makeReport())

    expect(r.reviewsError.value).toBe('复核数据加载失败，请稍后重试')
    expect(r.reviewsError.value).not.toContain('InactiveRpcError')
  })

  it('openManualReview 无结果行：reviewsError + notification.error，不打开弹窗', async () => {
    tasksApiMock.getCaseResults.mockResolvedValue({ results: [] })
    const r = useReportReviews(() => makeReport())
    await r.loadReportReviews(makeReport())

    await r.openManualReview({ id: 101, name: '用例A' })

    expect(r.reviewsError.value).toBe('来源任务未查询到该用例结果行，无法复核')
    expect(notifications.error).toHaveBeenCalledWith('来源任务未查询到该用例结果行，无法复核')
    expect(modalOpenMock).not.toHaveBeenCalled()
  })

  it('openManualReview 提交失败：reviewsError + notification.error（RPC 文本收敛为友好文案）', async () => {
    tasksApiMock.getCaseResults.mockResolvedValue({ results: [{ id: 5, executionStatus: 'completed', evaluationStatus: 'completed' }] })
    modalOpenMock.mockResolvedValue({ executionStatus: 'failed', evaluationStatus: undefined, comment: '改判失败' })
    reviewApiMock.submitReview.mockRejectedValue(
      new Error('<_InactiveRpcError of RPC that terminated with: status=StatusCode.UNAVAILABLE details="failed to connect...">'),
    )
    const r = useReportReviews(() => makeReport())
    await r.loadReportReviews(makeReport())

    await r.openManualReview({ id: 101, name: '用例A' })

    expect(r.reviewsError.value).toBe('人工复核提交失败，请稍后重试')
    expect(notifications.error).toHaveBeenCalledTimes(1)
    expect(notifications.error).toHaveBeenCalledWith('人工复核提交失败，请稍后重试', expect.any(String))
    expect(r.reviewsError.value).not.toContain('InactiveRpcError')
  })

  it('来源任务为空：openManualReview 置 reviewsError + toast', async () => {
    const r = useReportReviews(() => makeReport())
    await r.loadReportReviews({ id: 9, summaries: [{ metadata: {} }] })

    await r.openManualReview({ id: 101, name: '用例A' })

    expect(r.reviewsError.value).toBe('报告缺少来源任务，无法在报告页发起人工复核')
    expect(notifications.error).toHaveBeenCalledWith('报告缺少来源任务，无法在报告页发起人工复核')
  })
})

/**
 * 快速复核弹窗组件测试（INT-1064 迁移，19 规范 §5.5）。
 * 覆盖 P2 修复保留：verdict=uncertain（存疑）时隐藏「采纳为复核结果」钮 + 不调 adopt 端点
 * （存疑无明确判定可采纳，后端 adopt 要求至少一项改判状态，避免空载荷 400）；
 * verdict=passed 时采纳钮可见且单次调 adopt（**不补调 /tasks/results/review，双写留痕**）。
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  AiReviewRecord,
  AiReviewVerdict,
  CaseResultForReview,
} from '@/domain/models/review'

import { QuickAiReviewDialog } from '../quick-ai-review-dialog'

const requestAiReviewMock = vi.hoisted(() => vi.fn())
const adoptAiReviewMock = vi.hoisted(() => vi.fn())
const rejectAiReviewMock = vi.hoisted(() => vi.fn())
const fetchAiReviewHistoryMock = vi.hoisted(() => vi.fn())

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

function completedRecord(verdict: AiReviewVerdict): AiReviewRecord {
  return {
    id: 10,
    resultId: 5400,
    taskId: 417,
    testCaseId: 'case-1',
    dimensionId: null,
    status: 'completed',
    verdict,
    confidence: 0.85,
    reasoning: '测试理由',
    adopted: false,
    adoptedByUserId: null,
    adoptedAt: null,
    rejected: false,
    rejectedByUserId: null,
    rejectedAt: null,
    createdAt: '2026-10-20T00:00:00Z',
    updatedAt: null,
  }
}

function renderDialog(verdict: AiReviewVerdict) {
  requestAiReviewMock.mockResolvedValue(completedRecord(verdict))
  return render(
    <QuickAiReviewDialog
      open
      onOpenChange={vi.fn()}
      taskId={417}
      caseId='case-1'
      caseName='用例一'
      results={[singleResult]}
      evaluationStatus='failed'
    />
  )
}

async function reachCompleted(verdict: AiReviewVerdict) {
  renderDialog(verdict)
  await userEvent.click(screen.getByRole('button', { name: '发起快速复核' }))
  await waitFor(() => {
    expect(screen.getByText('AI 复核结论')).toBeInTheDocument()
  })
}

describe('QuickAiReviewDialog（快速复核，INT-1064 迁移）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchAiReviewHistoryMock.mockResolvedValue([])
  })

  it('verdict=uncertain：隐藏「采纳为复核结果」钮 + 提示走人工复核，不调 adopt 端点', async () => {
    await reachCompleted('uncertain')
    expect(screen.queryByRole('button', { name: '采纳为复核结果' })).not.toBeInTheDocument()
    expect(
      screen.getByText('存疑结论无明确判定可采纳，可驳回或忽略，或经人工复核确定结果')
    ).toBeInTheDocument()
    expect(adoptAiReviewMock).not.toHaveBeenCalled()
  })

  it('verdict=passed：采纳钮可见，点击后单次调 adopt（不补调 /tasks/results/review）', async () => {
    adoptAiReviewMock.mockResolvedValue(completedRecord('passed'))
    await reachCompleted('passed')
    const adoptBtn = screen.getByRole('button', { name: '采纳为复核结果' })
    expect(adoptBtn).toBeInTheDocument()
    await userEvent.click(adoptBtn)
    await waitFor(() => {
      expect(adoptAiReviewMock).toHaveBeenCalledWith(10, {
        evaluationStatus: 'completed',
        comment: '测试理由',
      })
    })
  })

  it('INT-1279：发起时按用例评估维度显式传 dimension_ids（真实库结果无 LLM 判分维度时避免 400）', async () => {
    requestAiReviewMock.mockResolvedValue(completedRecord('passed'))
    render(
      <QuickAiReviewDialog
        open
        onOpenChange={vi.fn()}
        taskId={417}
        caseId='case-1'
        caseName='用例一'
        results={[singleResult]}
        evaluationStatus='failed'
        dimensionIds={[121, 124, 125]}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: '发起快速复核' }))
    await waitFor(() => {
      expect(requestAiReviewMock).toHaveBeenCalledWith(417, 'case-1', {
        resultIds: [5400],
        dimensionIds: [121, 124, 125],
      })
    })
  })

  it('INT-1279：dimensionIds 为空数组时不发送 dimension_ids（走后端缺省口径）', async () => {
    requestAiReviewMock.mockResolvedValue(completedRecord('passed'))
    render(
      <QuickAiReviewDialog
        open
        onOpenChange={vi.fn()}
        taskId={417}
        caseId='case-1'
        caseName='用例一'
        results={[singleResult]}
        evaluationStatus='failed'
        dimensionIds={[]}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: '发起快速复核' }))
    await waitFor(() => {
      expect(requestAiReviewMock).toHaveBeenCalledWith(417, 'case-1', {
        resultIds: [5400],
      })
    })
  })

  it('INT-1545：容器任务下按记录归属 task_id 轮询历史（不用页面 taskId），推进到结论卡', async () => {
    // 页面 taskId=527（挑选合并容器任务），结果归属源任务 418；发起响应 item.task_id=418
    requestAiReviewMock.mockResolvedValue({
      ...completedRecord('passed'),
      status: 'running',
      verdict: 'uncertain',
      taskId: 418,
    })
    fetchAiReviewHistoryMock.mockImplementation(async (historyTaskId: number) =>
      historyTaskId === 418 ? [{ ...completedRecord('passed'), id: 10, taskId: 418 }] : []
    )
    render(
      <QuickAiReviewDialog
        open
        onOpenChange={vi.fn()}
        taskId={527}
        caseId='case-1'
        caseName='用例一'
        results={[{ ...singleResult, sourceTaskId: 418 }]}
        evaluationStatus='failed'
      />
    )
    await userEvent.click(screen.getByRole('button', { name: '发起快速复核' }))
    await waitFor(
      () => {
        expect(screen.getByText('AI 复核结论')).toBeInTheDocument()
      },
      { timeout: 5000 }
    )
    expect(fetchAiReviewHistoryMock).toHaveBeenCalledWith(418)
    expect(fetchAiReviewHistoryMock).not.toHaveBeenCalledWith(527)
  }, 10000)

  it('INT-1545 回归：普通任务仍按页面 taskId 轮询历史并推进到结论卡', async () => {
    requestAiReviewMock.mockResolvedValue({
      ...completedRecord('passed'),
      status: 'running',
      verdict: 'uncertain',
      taskId: 417,
    })
    fetchAiReviewHistoryMock.mockImplementation(async (historyTaskId: number) =>
      historyTaskId === 417 ? [{ ...completedRecord('passed'), id: 10, taskId: 417 }] : []
    )
    render(
      <QuickAiReviewDialog
        open
        onOpenChange={vi.fn()}
        taskId={417}
        caseId='case-1'
        caseName='用例一'
        results={[singleResult]}
        evaluationStatus='failed'
      />
    )
    await userEvent.click(screen.getByRole('button', { name: '发起快速复核' }))
    await waitFor(
      () => {
        expect(screen.getByText('AI 复核结论')).toBeInTheDocument()
      },
      { timeout: 5000 }
    )
    expect(fetchAiReviewHistoryMock).toHaveBeenCalledWith(417)
  }, 10000)
})

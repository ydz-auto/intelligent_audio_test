/**
 * AI 复核记录卡测试（INT-1064，19 规范 §5.5/§5.7）。
 * 后端 ai_reviews 记录落位后：status=completed → 结论/置信度/理由 + 采纳/驳回；
 * verdict=uncertain（存疑）→ 隐藏采纳钮（无明确判定可采纳）；status 未知值 → 容错回退原值
 * （§5.7 注记 2）。采纳动作由消费侧单次调 POST /ai-review/{id}/adopt（审核注记 1，不补调 review）。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { AiReviewRecord, AiReviewVerdict } from '@/domain/models/review'

import { AiReviewRecordCard } from '../ai-review-record-card'

function record(status: AiReviewRecord['status'], verdict?: AiReviewVerdict): AiReviewRecord {
  return {
    id: 10,
    resultId: 5400,
    taskId: 417,
    testCaseId: 'case-1',
    dimensionId: null,
    status,
    verdict: verdict ?? 'passed',
    confidence: 0.85,
    reasoning: '测试理由',
    adopted: false,
    adoptedByUserId: null,
    adoptedAt: null,
    rejected: false,
    rejectedByUserId: null,
    rejectedAt: null,
    createdAt: '2026-10-21T00:00:00Z',
    updatedAt: null,
  }
}

describe('AiReviewRecordCard', () => {
  it('completed + passed：展示结论/置信度/理由 + 采纳/驳回钮；点击采纳回调', async () => {
    const onAdopt = vi.fn()
    const onReject = vi.fn()
    render(
      <AiReviewRecordCard
        record={record('completed', 'passed')}
        originalEvaluationStatus='failed'
        onAdopt={onAdopt}
        onReject={onReject}
      />
    )
    expect(screen.getAllByText('复核通过').length).toBeGreaterThan(0)
    expect(screen.getByText('置信度 85%')).toBeInTheDocument()
    expect(screen.getByText('测试理由')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '采纳为复核结果' }))
    expect(onAdopt).toHaveBeenCalledTimes(1)
    await userEvent.click(screen.getByRole('button', { name: '驳回' }))
    expect(onReject).toHaveBeenCalledTimes(1)
  })

  it('completed + uncertain（存疑）：隐藏采纳钮 + 提示可驳回/人工复核', () => {
    render(
      <AiReviewRecordCard
        record={record('completed', 'uncertain')}
        onAdopt={vi.fn()}
        onReject={vi.fn()}
      />
    )
    expect(screen.queryByRole('button', { name: '采纳为复核结果' })).not.toBeInTheDocument()
    expect(
      screen.getByText('存疑结论无明确判定可采纳，可驳回或经人工复核确定结果')
    ).toBeInTheDocument()
  })

  it('status 未知值 → 容错回退原值展示（§5.7 注记 2），不抛错', () => {
    const weird = record('completed', 'passed')
    // 模拟后端出现未枚举 status（表 DEFAULT pending 兜底口径）
    render(
      <AiReviewRecordCard
        record={{ ...weird, status: 'reviewing_x' as AiReviewRecord['status'] }}
        onAdopt={vi.fn()}
        onReject={vi.fn()}
      />
    )
    // 未知 status 回退原值展示，结论字段仅 completed 展示
    expect(screen.getByText('reviewing_x')).toBeInTheDocument()
  })
})

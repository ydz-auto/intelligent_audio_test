/**
 * infrastructure/adapters（reviewAdapter + aiReviewAdapter）+ 复核领域模型 纯函数测试
 * （19 规范 §3.6/§4.4，INT-793；AI 复核契约定稿 INT-824）。
 * 对位 review_repository._review_po_to_dict / review_service.submit_review /
 * api_gateway/schemas/ai_review.py AiReviewRecordDto 实测响应形态。
 */
import { describe, expect, it } from 'vitest'

import {
  toReviewHistoryItem,
  toReviewHistoryList,
  toReviewSubmitResult,
} from '@/infrastructure/adapters/reviewAdapter'
import {
  toAiReviewRecord,
  toAiReviewHistoryList,
} from '@/infrastructure/adapters/aiReviewAdapter'
import {
  aiConfidenceLabel,
  aiReviewStatusLabel,
  evaluationStatusLabel,
  executionStatusLabel,
} from '@/domain/models/review'

describe('toReviewHistoryItem', () => {
  it('snake_case DTO → camelCase 领域（留痕行）', () => {
    expect(
      toReviewHistoryItem({
        id: 1,
        result_id: 5599,
        task_id: 407,
        test_case_id: '4607de9d-8a3e-4b96-8f12-b8c95bbb0c5e',
        field_name: 'evaluation_status',
        old_value: 'failed',
        new_value: 'completed',
        comment: '接线测试：INT-793 演示',
        created_by_user_id: 7,
        created_at: '2026-10-19T04:00:00',
      })
    ).toEqual({
      id: 1,
      resultId: 5599,
      taskId: 407,
      testCaseId: '4607de9d-8a3e-4b96-8f12-b8c95bbb0c5e',
      fieldName: 'evaluation_status',
      oldValue: 'failed',
      newValue: 'completed',
      comment: '接线测试：INT-793 演示',
      createdByUserId: 7,
      createdAt: '2026-10-19T04:00:00',
    })
  })

  it('空历史 → 空列表', () => {
    expect(toReviewHistoryList([])).toEqual([])
  })
})

describe('toReviewSubmitResult', () => {
  it('reviewed/failed/review_count → 领域', () => {
    expect(
      toReviewSubmitResult({
        reviewed: [{ result_id: 5599 }],
        failed: [{ result_id: 1, message: '状态无变化（已复核同值），仅允许补备注' }],
        review_count: 1,
      })
    ).toEqual({
      reviewedCount: 1,
      failed: [{ resultId: 1, message: '状态无变化（已复核同值），仅允许补备注' }],
    })
  })
})

describe('toAiReviewRecord', () => {
  it('AI 复核记录 DTO（ai_reviews 契约定稿）→ 领域（含 status/dimensionId/0-1 处置位）', () => {
    expect(
      toAiReviewRecord({
        id: 1001,
        result_id: 4690,
        task_id: 407,
        test_case_id: '86756aa2-2c97-4548-b493-b2312b20a8c4',
        dimension_id: 3,
        status: 'completed',
        verdict: 'passed',
        confidence: 0.85,
        reasoning: '大模型复检建议维持原评估结论',
        adopted: 1,
        adopted_by_user_id: 7,
        adopted_at: '2026-10-19T04:00:00',
        rejected: 0,
        rejected_by_user_id: null,
        rejected_at: null,
        created_at: '2026-10-19T04:00:00',
        updated_at: '2026-10-19T04:00:00',
      })
    ).toEqual({
      id: 1001,
      resultId: 4690,
      taskId: 407,
      testCaseId: '86756aa2-2c97-4548-b493-b2312b20a8c4',
      dimensionId: 3,
      status: 'completed',
      verdict: 'passed',
      confidence: 0.85,
      reasoning: '大模型复检建议维持原评估结论',
      adopted: true,
      adoptedByUserId: 7,
      adoptedAt: '2026-10-19T04:00:00',
      rejected: false,
      rejectedByUserId: null,
      rejectedAt: null,
      createdAt: '2026-10-19T04:00:00',
      updatedAt: '2026-10-19T04:00:00',
    })
  })

  it('执行中记录（无判定字段 + 未知 status）→ 领域容错（verdict 兜底 uncertain，status 原样）', () => {
    expect(
      toAiReviewRecord({
        id: 1002,
        result_id: 4691,
        task_id: 407,
        test_case_id: null,
        dimension_id: null,
        status: 'running',
        verdict: null,
        confidence: null,
        reasoning: null,
        adopted: 0,
        adopted_by_user_id: null,
        adopted_at: null,
        rejected: 0,
        rejected_by_user_id: null,
        rejected_at: null,
        created_at: '2026-10-19T04:00:00',
        updated_at: null,
      })
    ).toMatchObject({
      id: 1002,
      status: 'running',
      verdict: 'uncertain',
      confidence: 0,
      reasoning: '',
      adopted: false,
      rejected: false,
    })
  })

  it('空历史 → 空列表', () => {
    expect(toAiReviewHistoryList([])).toEqual([])
  })
})

describe('复核领域文案（§7 页面文案）', () => {
  it('执行/评估状态中文映射', () => {
    expect(executionStatusLabel('completed')).toBe('已完成')
    expect(executionStatusLabel('skipped')).toBe('已跳过')
    expect(executionStatusLabel('unknown-x')).toBe('unknown-x')
    expect(evaluationStatusLabel('failed')).toBe('评估失败')
    expect(evaluationStatusLabel(undefined)).toBe('未知')
  })

  it('AI 置信度 0-1 → 百分比', () => {
    expect(aiConfidenceLabel(0.85)).toBe('85%')
    expect(aiConfidenceLabel(undefined)).toBe('—')
  })

  it('AI 复核任务状态中文映射（未知值回退原值，表 DEFAULT pending 容错）', () => {
    expect(aiReviewStatusLabel('running')).toBe('复核中')
    expect(aiReviewStatusLabel('completed')).toBe('已完成')
    expect(aiReviewStatusLabel('failed')).toBe('失败')
    expect(aiReviewStatusLabel('pending')).toBe('排队中')
    expect(aiReviewStatusLabel('unknown-x')).toBe('unknown-x')
    expect(aiReviewStatusLabel(null)).toBe('未知')
  })
})

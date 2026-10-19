/**
 * 人工复核 + AI 复核 API（infrastructure/api，19_人工审核与AI复核交互设计.md §3.6/§4.4，INT-793）。
 * 真实接口（经 client.ts 统一信封解包）：
 *   POST /api/v1/tasks/results/review            （提交复核，task.result.review）
 *   GET  /api/v1/tasks/results/{task_id}/review-count  （已复核条数，task:read）
 *   GET  /api/v1/tasks/results/{task_id}/review-history（复核历史，task:read）
 *   GET  /api/v1/tasks/{task_id}/cases/{case_id}/results（用例执行结果：result_id/复核标注）
 * AI 复核契约定稿 INT-824（ai_reviews 表，权限 task.result.ai_review / 采纳 task.result.review）：
 *   POST /api/v1/tasks/results/ai-review           （发起，异步执行后落结论）
 *   GET  /api/v1/tasks/results/{task_id}/ai-review-history（该任务 AI 复核记录）
 *   POST /api/v1/tasks/results/ai-review/{id}/adopt（采纳，落人工复核语义 + 统计重算）
 *   POST /api/v1/tasks/results/ai-review/{id}/reject（驳回，原判定不变）
 */
import type {
  AiReviewAdoptPayload,
  AiReviewRecord,
  AiReviewRequest,
  CaseResultsForReview,
  ReviewHistoryItem,
  ReviewSubmitPayload,
  ReviewSubmitResult,
} from '@/domain/models/review'
import type {
  AiReviewAdoptResponseDto,
  AiReviewHistoryDataDto,
  AiReviewInitiateDataDto,
  AiReviewRecordDto,
  CaseResultsDataDto,
  ReviewCountDto,
  ReviewHistoryDataDto,
  ReviewSubmitResponseDto,
} from '@/infrastructure/dto/review.dto'
import {
  toAiReviewHistoryList,
  toAiReviewRecord,
  toCaseResultsForReview,
  toReviewHistoryList,
  toReviewSubmitResult,
} from '@/infrastructure/adapters/reviewAdapter'
import { ApiError } from './api-error'
import { request } from './client'

/** 提交复核（单条/批量逐条留痕；comment 必填） */
export async function submitReview(
  payload: ReviewSubmitPayload
): Promise<ReviewSubmitResult> {
  const dto = await request<ReviewSubmitResponseDto>(
    'POST',
    '/tasks/results/review',
    {
      result_ids: payload.resultIds,
      execution_status: payload.executionStatus || undefined,
      evaluation_status: payload.evaluationStatus || undefined,
      comment: payload.comment,
    }
  )
  return toReviewSubmitResult(dto)
}

/** 任务已复核结果计数（覆盖提醒 / 报告头统计徽章） */
export async function fetchReviewCount(taskId: number): Promise<number> {
  const dto = await request<ReviewCountDto>(
    'GET',
    `/tasks/results/${taskId}/review-count`
  )
  return dto.review_count ?? 0
}

/** 任务复核历史（多次复核追加不覆盖，时间倒序由消费侧排） */
export async function fetchReviewHistory(
  taskId: number
): Promise<ReviewHistoryItem[]> {
  const dto = await request<ReviewHistoryDataDto>(
    'GET',
    `/tasks/results/${taskId}/review-history`
  )
  return toReviewHistoryList(dto.items ?? [])
}

/** 用例执行结果（复核入口溯源：result_id + 复核标注 + 设备/API 名；task:read） */
export async function fetchCaseResults(
  taskId: number,
  caseId: string
): Promise<CaseResultsForReview> {
  const dto = await request<CaseResultsDataDto>(
    'GET',
    `/tasks/${taskId}/cases/${caseId}/results`
  )
  return toCaseResultsForReview(dto)
}

// ---------------------------------------------------------------------------
// AI 复核（INT-824 契约定稿：ai_reviews 表；发起/驳回 task.result.ai_review，
// 历史 task:read，采纳 task.result.review）
// ---------------------------------------------------------------------------

/** 发起 AI 复核（POST /tasks/results/ai-review；异步执行结论落位后由消费侧轮询历史） */
export async function requestAiReview(
  taskId: number,
  caseId: string,
  payload: AiReviewRequest
): Promise<AiReviewRecord> {
  // taskId/caseId 为调用侧溯源上下文（发起对象），后端按 result_ids 落记录
  void taskId
  void caseId
  const dto = await request<AiReviewInitiateDataDto>(
    'POST',
    '/tasks/results/ai-review',
    {
      result_ids: payload.resultIds,
      dimension_ids: payload.dimensionIds || undefined,
    }
  )
  const item = (dto.items ?? [])[0]
  if (!item) {
    const message = dto.skipped?.[0]?.message ?? 'AI 复核发起失败：未返回复核记录'
    throw new ApiError({ message })
  }
  return toAiReviewRecord(item)
}

/** AI 复核历史（GET /tasks/results/{task_id}/ai-review-history；可选 result_id/dimension_id/status 过滤） */
export async function fetchAiReviewHistory(
  taskId: number,
  filters?: { resultId?: number; dimensionId?: number; status?: string }
): Promise<AiReviewRecord[]> {
  const dto = await request<AiReviewHistoryDataDto>(
    'GET',
    `/tasks/results/${taskId}/ai-review-history`,
    undefined,
    {
      params: {
        result_id: filters?.resultId,
        dimension_id: filters?.dimensionId,
        status: filters?.status,
      },
    }
  )
  return toAiReviewHistoryList(dto.items ?? [])
}

/** 采纳 AI 结论（POST /tasks/results/ai-review/{id}/adopt；落人工复核语义 + 统计重算） */
export async function adoptAiReview(
  recordId: number,
  payload?: AiReviewAdoptPayload
): Promise<AiReviewRecord> {
  if (!payload) {
    throw new ApiError({
      message: '采纳 AI 复核结论需携带复核载荷（评估状态/执行状态 + 备注）',
    })
  }
  const dto = await request<AiReviewAdoptResponseDto>(
    'POST',
    `/tasks/results/ai-review/${recordId}/adopt`,
    {
      execution_status: payload.executionStatus || undefined,
      evaluation_status: payload.evaluationStatus || undefined,
      comment: payload.comment,
    }
  )
  if (!dto.item) {
    throw new ApiError({ message: '采纳 AI 复核结论失败：未返回更新后的复核记录' })
  }
  return toAiReviewRecord(dto.item)
}

/** 驳回 AI 结论（POST /tasks/results/ai-review/{id}/reject；原判定不变，标记已驳回备查） */
export async function rejectAiReview(recordId: number): Promise<AiReviewRecord> {
  const dto = await request<AiReviewRecordDto>(
    'POST',
    `/tasks/results/ai-review/${recordId}/reject`
  )
  return toAiReviewRecord(dto)
}

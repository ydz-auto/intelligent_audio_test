// -*- coding: utf-8 -*-
/**
 * AI 复核 API（19 规范 §5.2/§5.3，INT-862 接线）——建议层，不直接改统计。
 *
 * 真实接口（后端 INT-822/823/824 已合入，契约只读 api_gateway/routes/review_bp.py）：
 *   POST /tasks/results/ai-review                    # 发起（result_ids + dimension_ids?，权限 task.result.ai_review）
 *   GET  /tasks/results/{task_id}/ai-review-history  # AI 复核记录（task:read，时间倒序，可 result_id/status 过滤）
 *   POST /tasks/results/ai-review/{id}/adopt         # 采纳（task.result.review；后端落人工复核语义：改判+留痕+统计重算+标记采纳）
 *   POST /tasks/results/ai-review/{id}/reject        # 驳回（task.result.ai_review；原判定不变，记录标记驳回备查）
 *
 * 发起为异步执行：后端落 ai_reviews.status=running 后经 evaluation_service LLM 复检
 * 回写 verdict/confidence/reasoning 并置 completed（失败 failed 不落判定）。
 * 本层发起后轮询 ai-review-history 直至结论落库，返回可展示的 completed 记录。
 */
import { request } from '../http/client';
import { toAiReviewRecord } from '../adapters/reviewAdapter';
import type {
  AiReviewRecord, AiReviewPhase, AiReviewVerdict,
} from '../../domain/model/review';

export type { AiReviewPhase, AiReviewVerdict, AiReviewRecord } from '../../domain/model/review';

/** AI 复核发起载荷（result_ids + 可选复核维度） */
export interface AiReviewRequest {
  resultIds: number[]
  dimensionIds?: number[]
}

/** AI 结论中文（§7 文案） */
export const AI_VERDICT_LABELS: Record<AiReviewVerdict, string> = {
  passed: '复核通过',
  failed: '复核不通过',
  uncertain: '存疑',
}

/** 置信度展示（§4.3：{n}% 或高/中/低） */
export function aiConfidenceLabel(confidence: number): string {
  if (confidence >= 0.8) return '高'
  if (confidence >= 0.55) return '中'
  return '低'
}

// ---------------------------------------------------------------------------
// 轮询参数（异步回写结论：LLM 复检通常在秒级完成，15s 仍未完成则提示稍后查看）
// ---------------------------------------------------------------------------

const _POLL_MAX_TRIES = 15
const _POLL_INTERVAL_MS = 1000

async function _sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** 等待 AI 复核结论落库：轮询 ai-review-history 直至 completed/failed（超时抛错提示稍后查看） */
async function _waitForConclusion(
  taskId: number,
  reviewId: number,
  resultId: number,
): Promise<AiReviewRecord> {
  for (let i = 0; i < _POLL_MAX_TRIES; i++) {
    await _sleep(_POLL_INTERVAL_MS)
    const history = await fetchAiReviewHistory(taskId, { resultId })
    const rec = history.find((r) => r.id === reviewId)
    if (!rec) continue
    if (rec.status === 'completed') return rec
    if (rec.status === 'failed' || rec.status === 'canceled') {
      throw new Error(rec.reasoning || 'AI 复核执行未完成，请稍后重试')
    }
  }
  throw new Error('AI 复核仍在执行中，请稍后在复核历史中查看或重新发起')
}

/**
 * 发起 AI 复核（POST /tasks/results/ai-review）并等待结论落库。
 * 返回 completed 记录（幂等复用最近结论时直接返回）；失败/超时抛错由界面提示。
 */
export async function requestAiReview(
  taskId: number,
  _caseId: string,
  payload: AiReviewRequest,
): Promise<AiReviewRecord> {
  const data = await request<{ items?: Record<string, unknown>[]; reused?: boolean }>(
    'POST', '/tasks/results/ai-review', {
      result_ids: payload.resultIds.map((id) => Number(id)),
      dimension_ids: payload.dimensionIds?.map((id) => Number(id)) || undefined,
    },
  )
  const items = data?.items ?? []
  if (!items.length) throw new Error('AI 复核发起失败：该结果无可用复核维度（需已完成评估的 LLM 判分）')
  const first = toAiReviewRecord(items[0])
  if (first.status === 'completed' && first.verdict) return first
  if (first.status === 'failed' || first.status === 'canceled') {
    throw new Error(first.reasoning || 'AI 复核执行未完成，请稍后重试')
  }
  // running/pending → 轮询历史直至结论落库
  return _waitForConclusion(taskId, first.id, first.resultId)
}

/**
 * AI 复核历史（GET /tasks/results/{task_id}/ai-review-history，时间倒序）。
 * 可选 resultId / status 过滤（Query 对齐后端契约白名单 result_id/dimension_id/status）。
 */
export async function fetchAiReviewHistory(
  taskId: number,
  filters?: { resultId?: number; status?: string },
): Promise<AiReviewRecord[]> {
  const data = await request<{ items?: Record<string, unknown>[] }>(
    'GET', `/tasks/results/${taskId}/ai-review-history`, null, {
      params: {
        result_id: filters?.resultId,
        status: filters?.status,
      },
    },
  )
  return (data?.items ?? []).map(toAiReviewRecord)
}

/**
 * 采纳 AI 复核结论（POST /tasks/results/ai-review/{id}/adopt）。
 * 载荷对齐人工复核契约：execution_status?/evaluation_status?（至少一项）+ comment 必填；
 * 后端单事务落 test_result_reviews 留痕 + 统计重算 + 标记 ai_reviews.adopted。
 */
export async function adoptAiReview(
  recordId: number,
  payload: { executionStatus?: string; evaluationStatus?: string; comment: string },
): Promise<AiReviewRecord> {
  const data = await request<{ item?: Record<string, unknown> }>(
    'POST', `/tasks/results/ai-review/${recordId}/adopt`, {
      execution_status: payload.executionStatus || undefined,
      evaluation_status: payload.evaluationStatus || undefined,
      comment: payload.comment,
    },
  )
  return toAiReviewRecord(data?.item ?? {})
}

/** 驳回 AI 复核结论（POST /tasks/results/ai-review/{id}/reject；原判定不变，记录标记驳回备查） */
export async function rejectAiReview(recordId: number): Promise<AiReviewRecord> {
  const data = await request<Record<string, unknown>>(
    'POST', `/tasks/results/ai-review/${recordId}/reject`,
  )
  return toAiReviewRecord(data ?? {})
}

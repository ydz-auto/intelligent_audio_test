// -*- coding: utf-8 -*-
/**
 * AI 复核 API（19 规范 §5.2/§5.3，INT-796/INT-1068）——建议层，不直接改统计。
 *
 * 真实端点（INT-800 已落地，契约定稿 schemas/ai_review.py + review_bp.py，前缀 /api/v1/tasks/results）：
 *   POST /tasks/results/ai-review                { result_ids:[int]≥1, dimension_ids?:[int], force?:boolean }
 *   GET  /tasks/results/{task_id}/ai-review-history   Query result_id/dimension_id/status（时间倒序）
 *   POST /tasks/results/ai-review/{id}/adopt     { execution_status?, evaluation_status?, comment(必填) }
 *   POST /tasks/results/ai-review/{id}/reject    {}
 *
 * INT-1068：由 `// 待接线` 会话级内存桩切换真实请求；采纳为单次 adopt
 * （adopt 端点内部复用人工复核 apply_review 落 test_result_reviews，前端不补调
 * /tasks/results/review，防双写留痕）。
 */
import { request } from '../http/client';
import { toAiReviewRecord } from '../adapters/reviewAdapter';
import type { AiReviewRecord, AiReviewAdoptPayload } from '../../domain/model/review';

/** AI 复核结论判定（历史兼容导出；域判定类型统一在 domain/model/review） */
export type AiReviewVerdict = 'passed' | 'failed' | 'uncertain'

/** AI 复核发起载荷（result_ids + 可选复核维度 + force 幂等绕过） */
export interface AiReviewRequest {
  resultIds: number[]
  dimensionIds?: number[]
  force?: boolean
}

export type AiReviewPhase = 'idle' | 'running' | 'completed' | 'adopted' | 'rejected'

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

/** 发起 AI 复核（POST /tasks/results/ai-review；幂等：同结果同维度已有时后端复用最近结论）。
 * taskId/caseId 不参与请求（端点为结果级，路径无 task_id），签名只保留载荷。 */
export async function requestAiReview(
  payload: AiReviewRequest,
): Promise<AiReviewRecord> {
  const raw = await request<{ items?: Record<string, unknown>[] }>('POST', '/tasks/results/ai-review', {
    result_ids: payload.resultIds.map((id) => Number(id)),
    dimension_ids: payload.dimensionIds && payload.dimensionIds.length > 0
      ? payload.dimensionIds.map((id) => Number(id))
      : undefined,
    force: payload.force,
  });
  const item = raw?.items?.[0];
  if (!item) throw new Error('AI 复核发起后未返回记录');
  return toAiReviewRecord(item);
}

/**
 * AI 复核历史（GET /tasks/results/{task_id}/ai-review-history）。
 * 可选按 result_id / dimension_id / status 过滤（§5.3 幂等复用 + §5.6 轮询）。
 */
export async function fetchAiReviewHistory(
  taskId: number | string,
  filters?: { resultId?: number | string; dimensionId?: number | string; status?: string },
): Promise<AiReviewRecord[]> {
  const raw = await request<{ items?: Record<string, unknown>[] }>(
    'GET',
    `/tasks/results/${taskId}/ai-review-history`,
    null,
    {
      params: {
        result_id: filters?.resultId,
        dimension_id: filters?.dimensionId,
        status: filters?.status,
      },
    },
  );
  return (raw?.items ?? []).map(toAiReviewRecord);
}

/** 采纳 AI 结论（POST /tasks/results/ai-review/{id}/adopt）——单次调用落人工复核语义，前端不补调 review */
export async function adoptAiReview(
  recordId: number,
  payload: AiReviewAdoptPayload,
): Promise<AiReviewRecord> {
  const raw = await request<{ item?: Record<string, unknown> }>(
    'POST',
    `/tasks/results/ai-review/${recordId}/adopt`,
    {
      execution_status: payload.executionStatus || undefined,
      evaluation_status: payload.evaluationStatus || undefined,
      comment: payload.comment,
    },
  );
  if (!raw?.item) throw new Error('采纳后未返回 AI 复核记录');
  return toAiReviewRecord(raw.item);
}

/** 驳回 AI 结论（POST /tasks/results/ai-review/{id}/reject，{}；原判定不变，记录标记已驳回备查） */
export async function rejectAiReview(recordId: number): Promise<AiReviewRecord> {
  const raw = await request<Record<string, unknown>>(
    'POST',
    `/tasks/results/ai-review/${recordId}/reject`,
    {},
  );
  return toAiReviewRecord(raw);
}

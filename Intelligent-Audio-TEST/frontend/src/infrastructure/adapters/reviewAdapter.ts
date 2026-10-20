/**
 * Review Adapter —— DTO(snake_case) → Domain(camelCase)
 *
 * 复核留痕 / AI 复核记录转换；分层对齐 W1-A：infrastructure/adapters 是
 * 唯一做 snake_case↔camelCase 转换的层，业务层只见 camelCase 领域对象。
 */
import type { ReviewHistoryItemDomain, AiReviewRecord, AiReviewConfidence, AiReviewVerdict } from '../../domain/model/review';
import { s } from './report.utils';

/** 复核留痕行 → ReviewHistoryItemDomain（容忍缺省/空值） */
export function toReviewHistoryDomain(raw: Record<string, unknown>): ReviewHistoryItemDomain {
  return {
    id: raw.id !== undefined && raw.id !== null ? Number(raw.id) : undefined,
    resultId: raw.result_id !== undefined && raw.result_id !== null ? Number(raw.result_id) : undefined,
    taskId: raw.task_id !== undefined && raw.task_id !== null ? Number(raw.task_id) : undefined,
    testCaseId: raw.test_case_id === null || raw.test_case_id === undefined ? null : s(raw.test_case_id),
    fieldName: raw.field_name === null || raw.field_name === undefined ? undefined : s(raw.field_name) as ReviewHistoryItemDomain['fieldName'],
    oldValue: raw.old_value === null || raw.old_value === undefined ? null : s(raw.old_value),
    newValue: raw.new_value === null || raw.new_value === undefined ? null : s(raw.new_value),
    comment: raw.comment === null || raw.comment === undefined ? null : s(raw.comment),
    createdByUserId: raw.created_by_user_id === null || raw.created_by_user_id === undefined
      ? null
      : Number(raw.created_by_user_id),
    createdAt: raw.created_at === null || raw.created_at === undefined ? null : s(raw.created_at),
  };
}

/** AI 复核记录 → AiReviewRecord（后端表 ai_reviews 全字段，INT-800 契约定稿） */
export function toAiReviewRecord(raw: Record<string, unknown>): AiReviewRecord {
  const confidenceRaw = raw.confidence;
  const confidenceValue = typeof confidenceRaw === 'number' ? confidenceRaw : Number(confidenceRaw ?? 0);
  const confidence: AiReviewConfidence = {
    value: confidenceValue,
    label: confidenceValue >= 0.8 ? '高' : confidenceValue >= 0.5 ? '中' : '低',
  };
  const verdictRaw = s(raw.verdict);
  // 缺省/未知 verdict 保留 null（域类型 AiReviewVerdict | null），渲染侧按状态门控
  // （running/failed 等非 completed 记录不得伪造结论；§5.7 容错口径，P2-1）
  const verdict: AiReviewVerdict | null =
    verdictRaw === 'passed' || verdictRaw === 'failed' || verdictRaw === 'uncertain' ? verdictRaw : null;

  return {
    id: Number(raw.id ?? 0),
    resultId: Number(raw.result_id ?? 0),
    taskId: Number(raw.task_id ?? 0),
    testCaseId: raw.test_case_id === null || raw.test_case_id === undefined ? null : s(raw.test_case_id),
    dimensionId: raw.dimension_id === null || raw.dimension_id === undefined ? null : Number(raw.dimension_id),
    dimensionName: raw.dimension_name === null || raw.dimension_name === undefined ? null : s(raw.dimension_name),
    status: raw.status === null || raw.status === undefined ? null : s(raw.status) as AiReviewRecord['status'],
    verdict,
    confidence,
    reasoning: raw.reasoning === null || raw.reasoning === undefined ? '' : s(raw.reasoning),
    originalEvaluationStatus:
      raw.original_evaluation_status === null || raw.original_evaluation_status === undefined
        ? null
        : s(raw.original_evaluation_status),
    adopted: Boolean(raw.adopted),
    adoptedByUserId: raw.adopted_by_user_id === null || raw.adopted_by_user_id === undefined
      ? null
      : Number(raw.adopted_by_user_id),
    adoptedAt: raw.adopted_at === null || raw.adopted_at === undefined ? null : s(raw.adopted_at),
    rejected: Boolean(raw.rejected),
    rejectedByUserId: raw.rejected_by_user_id === null || raw.rejected_by_user_id === undefined
      ? null
      : Number(raw.rejected_by_user_id),
    rejectedAt: raw.rejected_at === null || raw.rejected_at === undefined ? null : s(raw.rejected_at),
    createdAt: raw.created_at === null || raw.created_at === undefined ? '' : s(raw.created_at),
    updatedAt: raw.updated_at === null || raw.updated_at === undefined ? null : s(raw.updated_at),
  };
}

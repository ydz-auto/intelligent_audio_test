/**
 * 复核 API —— 人工审核（真实接口 INT-340）+ AI 复核（真实接口 INT-800，INT-1068 接线）
 *
 * 出口契约：Domain（camelCase）；DTO 转换收敛在 adapters。
 * - 人工审核：POST /tasks/results/review、GET /tasks/results/{task_id}/review-count|review-history
 *   （同 tasksApi，报告页消费侧独立收敛，避免跨域直接引用任务域 api）
 * - AI 复核：真实端点委托 reviewAiApi（发起/历史/采纳/驳回；采纳单次 adopt 防双写留痕）
 */
import { request } from '../http/client';
import type { ReviewSubmitPayload, ReviewHistoryItemDomain, AiReviewRecord, AiReviewAdoptPayload } from '../../domain/model/review';
import { toReviewHistoryDomain } from '../adapters/reviewAdapter';
import {
  requestAiReview as submitAiReviewRequest,
  fetchAiReviewHistory,
  adoptAiReview as adoptAiReviewRequest,
  rejectAiReview as rejectAiReviewRequest,
} from './reviewAiApi';

export const reviewApi = {
  /**
   * 人工复核提交（单条/批量逐条留痕；comment 必填）。
   * 载荷经 ReviewSubmitPayload（camelCase）→ snake_case DTO 转换。
   */
  async submitReview(payload: ReviewSubmitPayload): Promise<void> {
    await request('POST', '/tasks/results/review', {
      result_ids: payload.resultIds.map((id) => Number(id)),
      execution_status: payload.executionStatus || undefined,
      evaluation_status: payload.evaluationStatus || undefined,
      comment: payload.comment,
    });
  },

  /** 任务下已复核结果条数（报告页复核统计徽章数据源之一） */
  async getReviewCount(taskId: string | number): Promise<number> {
    const raw = await request<{ review_count?: number }>('GET', `/tasks/results/${taskId}/review-count`);
    return raw?.review_count ?? 0;
  },

  /** 任务复核历史（多次复核追加不覆盖；含 test_case_id，报告页按用例聚合） */
  async getReviewHistory(taskId: string | number): Promise<ReviewHistoryItemDomain[]> {
    const raw = await request<{ items?: Record<string, unknown>[] }>('GET', `/tasks/results/${taskId}/review-history`);
    return (raw?.items ?? []).map(toReviewHistoryDomain);
  },

  /** 发起 AI 复核（POST /tasks/results/ai-review；委托 reviewAiApi 真实端点） */
  async submitAiReview(payload: { resultIds: (string | number)[]; dimensionIds?: number[]; force?: boolean }): Promise<AiReviewRecord> {
    return submitAiReviewRequest({
      resultIds: payload.resultIds.map((id) => Number(id)),
      dimensionIds: payload.dimensionIds,
      force: payload.force,
    });
  },

  /** 查询 AI 复核历史（GET /tasks/results/{task_id}/ai-review-history；委托真实端点） */
  async getAiReviewHistory(taskId: string | number): Promise<AiReviewRecord[]> {
    return fetchAiReviewHistory(taskId);
  },

  /** 采纳 AI 复核结论（POST /tasks/results/ai-review/{id}/adopt；单次落人工复核语义，防双写留痕） */
  async adoptAiReview(aiReviewId: number, payload?: AiReviewAdoptPayload): Promise<AiReviewRecord> {
    return adoptAiReviewRequest(aiReviewId, payload ?? { comment: '' });
  },

  /** 驳回 AI 复核结论（POST /tasks/results/ai-review/{id}/reject；原判定不变，记录标记已驳回） */
  async rejectAiReview(aiReviewId: number): Promise<AiReviewRecord> {
    return rejectAiReviewRequest(aiReviewId);
  },
};

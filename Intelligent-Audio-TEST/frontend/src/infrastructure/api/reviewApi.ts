/**
 * 复核 API —— 人工审核（真实接口 INT-340）+ AI 复核（真实接口 INT-822/823/824）
 *
 * 出口契约：Domain（camelCase）；DTO 转换收敛在 adapters。
 * - 人工审核：POST /tasks/results/review、GET /tasks/results/{task_id}/review-count|review-history
 *   （同 tasksApi，报告页消费侧独立收敛，避免跨域直接引用任务域 api）
 * - AI 复核：端点见 reviewAiApi.ts（发起/历史/采纳/驳回，异步回写结论）；
 *   本段委派 reviewAiApi，避免双实现口径。
 */
import { request } from '../http/client';
import type { ReviewSubmitPayload, ReviewHistoryItemDomain, AiReviewRecord } from '../../domain/model/review';
import { toReviewHistoryDomain } from '../adapters/reviewAdapter';
import {
  requestAiReview,
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

  /**
   * 发起 AI 复核（POST /tasks/results/ai-review，异步回写结论；委派 reviewAiApi）。
   * 轮询 ai-review-history 直至 completed 返回记录；失败/超时抛错由调用方提示。
   */
  async submitAiReview(
    taskId: string | number,
    payload: { resultIds: (string | number)[]; dimensionIds?: number[] },
  ): Promise<AiReviewRecord> {
    return requestAiReview(Number(taskId), '', {
      resultIds: payload.resultIds.map((id) => Number(id)),
      dimensionIds: payload.dimensionIds?.map((id) => Number(id)),
    });
  },

  /** 查询 AI 复核历史（GET /tasks/results/{task_id}/ai-review-history，委派 reviewAiApi）。 */
  async getAiReviewHistory(taskId: string | number, filters?: { resultId?: number; status?: string }): Promise<AiReviewRecord[]> {
    return fetchAiReviewHistory(Number(taskId), filters);
  },

  /**
   * 采纳 AI 复核结论（POST /tasks/results/ai-review/{id}/adopt，委派 reviewAiApi）。
   * 载荷 executionStatus?/evaluationStatus? + comment 必填；后端落人工复核语义（改判+留痕+统计重算+标记采纳）。
   */
  async adoptAiReview(
    aiReviewId: number,
    payload: { executionStatus?: string; evaluationStatus?: string; comment: string },
  ): Promise<AiReviewRecord> {
    return adoptAiReviewRequest(aiReviewId, payload);
  },

  /** 驳回 AI 复核结论（POST /tasks/results/ai-review/{id}/reject，委派 reviewAiApi；原判定不变）。 */
  async rejectAiReview(aiReviewId: number): Promise<AiReviewRecord> {
    return rejectAiReviewRequest(aiReviewId);
  },
};

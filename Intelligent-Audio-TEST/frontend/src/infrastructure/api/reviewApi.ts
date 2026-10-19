/**
 * 复核 API —— 人工审核（真实接口 INT-340）+ AI 复核（`// 待接线` 桩，§8-2 待后端立项）
 *
 * 出口契约：Domain（camelCase）；DTO 转换收敛在 adapters。
 * - 人工审核：POST /tasks/results/review、GET /tasks/results/{task_id}/review-count|review-history
 *   （同 tasksApi，报告页消费侧独立收敛，避免跨域直接引用任务域 api）
 * - AI 复核：后端无端点（§8-2 待后端立项），此处留桩返回符合 §5.3 建议 schema 的示例数据，
 *   代码标 `// 待接线`；FEAT 落地后由接线卡替换为真实请求。
 */
import { request } from '../http/client';
import type { ReviewSubmitPayload, ReviewHistoryItemDomain, AiReviewRecord } from '../../domain/model/review';
import { toReviewHistoryDomain, toAiReviewRecord } from '../adapters/reviewAdapter';

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
   * 发起 AI 复核（§8-2 待后端立项）。
   * `// 待接线`：返回符合 §5.3 建议 schema 的示例结论，供交互流程验证；
   * FEAT 落地后替换为 POST /tasks/results/ai-review。
   */
  async submitAiReview(payload: { resultIds: (string | number)[]; dimensionIds?: number[] }): Promise<AiReviewRecord> {
    // 待接线：POST /tasks/results/ai-review
    void payload;
    await new Promise((resolve) => setTimeout(resolve, 600));
    return toAiReviewRecord({
      id: Math.floor(Math.random() * 100000),
      result_id: Number(payload.resultIds[0]),
      task_id: 0,
      test_case_id: null,
      dimension_id: payload.dimensionIds?.[0] ?? null,
      dimension_name: null,
      verdict: 'passed',
      confidence: 0.86,
      reasoning: '大模型复核：该用例评估结果与参考依据一致，判定通过（示例数据，待后端 AI 复核机制落地）。',
      original_evaluation_status: null,
      adopted: false,
      rejected: false,
      created_at: new Date().toISOString(),
    });
  },

  /** 查询 AI 复核历史（§8-2 待后端立项）。`// 待接线`：返回空列表示例。 */
  async getAiReviewHistory(_taskId: string | number): Promise<AiReviewRecord[]> {
    // 待接线：GET /tasks/results/{task_id}/ai-review-history
    return [];
  },

  /** 采纳 AI 复核结论 → 落人工复核语义（§8-2 待后端立项）。`// 待接线`：幂等成功。 */
  async adoptAiReview(_aiReviewId: number): Promise<void> {
    // 待接线：POST /tasks/results/ai-review/{id}/adopt
  },

  /** 驳回 AI 复核结论（§8-2 待后端立项）。`// 待接线`：幂等成功。 */
  async rejectAiReview(_aiReviewId: number): Promise<void> {
    // 待接线：POST /tasks/results/ai-review/{id}/reject
  },
};

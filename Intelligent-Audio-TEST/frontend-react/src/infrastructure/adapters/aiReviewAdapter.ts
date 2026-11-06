/**
 * AI 复核 DTO → 领域模型适配器（infrastructure 层，19 §5.7 / INT-1063 去桩）。
 * snake_case → camelCase 收敛只发生在本层；interfaces/application 只消费 camelCase。
 * 对位后端契约定稿（api_gateway/schemas/ai_review.py AiReviewRecordDto，ai_reviews 表全字段透传）：
 *   status(pending/running/completed/failed/canceled) / verdict?/confidence?/reasoning?
 *   adopted/rejected 为 0/1 整数；verdict/confidence/reasoning 执行中为 null。
 * 未知 status 值原样保留，由消费侧 aiReviewStatusLabel 容错渲染（§5.7 注记 2）。
 */
import type {
  AiReviewRecord,
  AiReviewRecordStatus,
} from '@/domain/models/review'
import type { AiReviewRecordDto } from '@/infrastructure/dto/review.dto'

/** AI 复核记录：DTO（ai_reviews 契约定稿 INT-824）→ 领域 */
export function toAiReviewRecord(dto: AiReviewRecordDto): AiReviewRecord {
  return {
    id: dto.id,
    resultId: dto.result_id,
    taskId: dto.task_id,
    testCaseId: dto.test_case_id ?? '',
    dimensionId: dto.dimension_id,
    // 未知 status 原样透传，消费侧容错渲染（表 DEFAULT pending，实际 running/completed/failed）
    status: dto.status as AiReviewRecordStatus,
    // 执行中/失败的记录无判定字段；领域模型非空契约，消费侧仅在 completed 展示
    verdict: dto.verdict ?? 'uncertain',
    confidence: dto.confidence ?? 0,
    reasoning: dto.reasoning ?? '',
    adopted: dto.adopted === 1,
    adoptedByUserId: dto.adopted_by_user_id,
    adoptedAt: dto.adopted_at,
    rejected: dto.rejected === 1,
    rejectedByUserId: dto.rejected_by_user_id,
    rejectedAt: dto.rejected_at,
    createdAt: dto.created_at ?? '',
    updatedAt: dto.updated_at,
  }
}

/** AI 复核历史：DTO items → 领域 */
export function toAiReviewHistoryList(
  items: AiReviewRecordDto[]
): AiReviewRecord[] {
  return (items ?? []).map(toAiReviewRecord)
}

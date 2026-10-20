/**
 * 人工复核 + AI 复核 DTO → 领域模型适配器（infrastructure 层，INT-793）。
 * snake_case → camelCase 收敛只发生在本层；interfaces/application 只消费 camelCase。
 * 对位后端实测响应（review_repository._review_po_to_dict / task_read_model_case_results
 * / review_service.submit_review）。
 */
import type {
  ReviewHistoryItem,
  ReviewSubmitResult,
  CaseResultForReview,
  CaseResultsForReview,
} from '@/domain/models/review'
import type {
  ReviewHistoryItemDto,
  ReviewSubmitResponseDto,
  CaseResultForReviewDto,
} from '@/infrastructure/dto/review.dto'

/** 复核留痕行：DTO → 领域（snake_case → camelCase） */
export function toReviewHistoryItem(dto: ReviewHistoryItemDto): ReviewHistoryItem {
  return {
    id: dto.id,
    resultId: dto.result_id,
    taskId: dto.task_id,
    testCaseId: dto.test_case_id,
    fieldName: dto.field_name,
    oldValue: dto.old_value,
    newValue: dto.new_value,
    comment: dto.comment,
    createdByUserId: dto.created_by_user_id,
    createdAt: dto.created_at,
  }
}

/** 复核历史列表：DTO items → 领域 */
export function toReviewHistoryList(
  items: ReviewHistoryItemDto[]
): ReviewHistoryItem[] {
  return (items ?? []).map(toReviewHistoryItem)
}

/** 复核提交响应：DTO → 领域（reviewed 明细为后端留痕摘要，前端只消费计数 + 未生效） */
export function toReviewSubmitResult(dto: ReviewSubmitResponseDto): ReviewSubmitResult {
  return {
    reviewedCount: dto.review_count ?? 0,
    failed: (dto.failed ?? []).map((f) => ({
      resultId: f.result_id,
      message: f.message,
    })),
  }
}

/** 用例执行结果行（复核消费侧字段子集；执行状态/设备名/API 名/复核标注） */
export function toCaseResultForReview(dto: CaseResultForReviewDto): CaseResultForReview {
  return {
    id: dto.id,
    deviceId: dto.device_id,
    deviceName: dto.device_name,
    apiId: dto.api_id,
    apiName: dto.api_name,
    executionStatus: dto.execution_status,
    responseTime: dto.response_time,
    errorMessage: dto.error_message,
    reviewed: dto.reviewed,
    reviewedByUserId: dto.reviewed_by_user_id,
    reviewedAt: dto.reviewed_at,
    lastReviewComment: dto.last_review_comment,
    lastReviewAction: dto.last_review_action,
    reviewHistory: toReviewHistoryList(dto.review_history ?? []),
    sourceTaskId: dto.source_task_id,
    sourceTaskName: dto.source_task_name,
  }
}

/** 用例执行结果响应 → 消费侧（caseName + results[]） */
export function toCaseResultsForReview(data: {
  task_id: number
  case_id: string
  case_name: string
  results: CaseResultForReviewDto[]
}): CaseResultsForReview {
  return {
    taskId: data.task_id,
    caseId: data.case_id,
    caseName: data.case_name,
    results: (data.results ?? []).map(toCaseResultForReview),
  }
}

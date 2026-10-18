/**
 * 人工复核 + AI 复核 DTO（infrastructure/dto，19_人工审核与AI复核交互设计.md §3.6/§4.4，INT-793）。
 * 对照 review_bp.py / schemas/review.py / task_service review_repository 实测响应形态。
 * snake_case 唯一出现层；经 adapters/reviewAdapter.ts 转 camelCase Domain。
 * AI 复核端点待后端立项（§8-2）→ dto 为契约建议形态，仅被桩返回。
 */

/** 复核留痕行（GET /tasks/results/{task_id}/review-history items；_review_po_to_dict 实测） */
export interface ReviewHistoryItemDto {
  id: number
  result_id: number
  task_id: number
  test_case_id: string
  field_name: 'execution_status' | 'evaluation_status'
  old_value: string | null
  new_value: string | null
  comment: string
  created_by_user_id: number | null
  created_at: string | null
}

/** 复核计数（GET /tasks/results/{task_id}/review-count） */
export interface ReviewCountDto {
  review_count: number
}

/** 复核历史列表（GET /tasks/results/{task_id}/review-history） */
export interface ReviewHistoryDataDto {
  items: ReviewHistoryItemDto[]
}

/** 复核提交响应（review_service.submit_review 实测：reviewed/failed/review_count） */
export interface ReviewSubmitResponseDto {
  reviewed: unknown[]
  failed: Array<{ result_id: number; message: string }>
  review_count: number
}

/** 用例执行结果行（GET /tasks/{task_id}/cases/{case_id}/results，INT-340 复核字段实测） */
export interface CaseResultForReviewDto {
  id: number
  device_id: number | null
  device_name: string | null
  api_id: number | null
  api_name: string | null
  execution_status: string | null
  response_time: number | null
  error_message: string | null
  reviewed: boolean
  reviewed_by_user_id: number | null
  reviewed_at: string | null
  last_review_comment: string | null
  last_review_action: string | null
  review_history: ReviewHistoryItemDto[]
  source_task_id: number
  source_task_name: string | null
}

/** 用例执行结果响应（get_case_results 实测：task_id/case_id/case_name/results） */
export interface CaseResultsDataDto {
  task_id: number
  case_id: string
  case_name: string
  results: CaseResultForReviewDto[]
}

// ---------------------------------------------------------------------------
// AI 复核（§5.3 契约建议；落地前仅桩返回，代码标 `// 待接线`）
// ---------------------------------------------------------------------------

/** AI 复核记录（§5.3 ai_reviews 契约建议） */
export interface AiReviewRecordDto {
  id: number
  result_id: number
  task_id: number
  test_case_id: string
  verdict: 'passed' | 'failed' | 'uncertain'
  confidence: number
  reasoning: string
  adopted: boolean
  adopted_by_user_id: number | null
  adopted_at: string | null
  rejected: boolean
  created_at: string
}

/** AI 复核历史（GET /tasks/results/{task_id}/ai-review-history 契约建议） */
export interface AiReviewHistoryDataDto {
  items: AiReviewRecordDto[]
}

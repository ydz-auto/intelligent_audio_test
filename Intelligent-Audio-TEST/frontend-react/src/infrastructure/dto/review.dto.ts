/**
 * 人工复核 + AI 复核 DTO（infrastructure/dto，19_人工审核与AI复核交互设计.md §3.6/§4.4，INT-793）。
 * 对照 review_bp.py / schemas/review.py / schemas/ai_review.py / task_service review_repository
 * / ai_review_repository 实测响应形态。
 * snake_case 唯一出现层；经 adapters 转 camelCase Domain。
 * AI 复核契约定稿 INT-824（ai_reviews 表），真实请求经 client.ts 统一信封解包（INT-1063 去桩）。
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

/**
 * 结果行评估维度（GET /tasks/{task_id}/cases/{case_id}/results results[].dimensions 实测）：
 * round_number NULL=整体评估、0 起=该轮；value 为原始指标值（null 表示本次未产出）。
 * dimension_type / parent_dimension_*（评分指标主/子层级；INT-2088）为可选字段——task_service
 * ACL 现不下发，前端读到即用（V9.7.10 comparisonData 同口径），读不到按主维度平铺。
 */
export interface CaseResultDimensionDto {
  dimension_id: number | null
  name: string
  value: unknown
  score: number | null
  status: string | null
  evaluation_status: string | null
  error_message: string | null
  round_number: number | null
  /** 主/子维度（缺省前端按 main 处理；当前后端 ACL 不下发） */
  dimension_type?: string | null
  parent_dimension_id?: number | null
  parent_dimension_name?: string | null
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
  /** 结果行评估维度（INT-1688：用例详情弹窗维度列数据源） */
  dimensions?: CaseResultDimensionDto[] | null
  /** 设备侧 ASR 识别结果（旧 Vue TestCaseDetailModal asr_result 同源） */
  asr_result?: string | null
  /** 设备侧翻译结果 */
  translation_result?: string | null
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
// AI 复核（INT-824 契约定稿：api_gateway/schemas/ai_review.py AiReviewRecordDto，
// task_service ai_reviews 表全字段透传；INT-1063 去桩切真实请求）
// ---------------------------------------------------------------------------

/** AI 复核记录（ai_reviews 全字段；adopted/rejected 为 0/1 整数，status 任务状态） */
export interface AiReviewRecordDto {
  id: number
  result_id: number
  task_id: number
  test_case_id: string | null
  dimension_id: number | null
  /** AI 复核任务状态（表 DEFAULT pending，实际 running/completed/failed；前端容错未知值） */
  status: string
  verdict: 'passed' | 'failed' | 'uncertain' | null
  confidence: number | null
  reasoning: string | null
  adopted: number
  adopted_by_user_id: number | null
  adopted_at: string | null
  rejected: number
  rejected_by_user_id: number | null
  rejected_at: string | null
  created_at: string | null
  updated_at: string | null
}

/** 发起 AI 复核响应（POST /tasks/results/ai-review：items + reused + skipped） */
export interface AiReviewInitiateDataDto {
  items: AiReviewRecordDto[]
  reused: boolean
  skipped: Array<{ result_id: number; message: string }>
}

/** AI 复核历史（GET /tasks/results/{task_id}/ai-review-history） */
export interface AiReviewHistoryDataDto {
  items: AiReviewRecordDto[]
}

/** 采纳 AI 复核响应（POST /tasks/results/ai-review/{id}/adopt：item + applied） */
export interface AiReviewAdoptResponseDto {
  item: AiReviewRecordDto
  applied: unknown[]
}

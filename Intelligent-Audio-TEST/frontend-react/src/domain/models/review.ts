/**
 * 人工复核 + AI 复核领域模型（19_人工审核与AI复核交互设计.md §3.6/§4.4，INT-793）。
 * 后端契约实测（INT-340/INT-762/INT-824）：review.py 改判枚举（执行 completed/failed/stopped/skipped，
 * 评估 completed/failed 双状态）+ comment 必填；test_result_reviews 留痕行；AI 复核契约定稿
 * （INT-824，ai_reviews 表：status/verdict/confidence/reasoning/adopted/rejected）。
 * snake_case↔camelCase 只在 infrastructure 层做，本层只见 camelCase 领域对象。
 */

/** 复核留痕字段名（test_result_reviews.field_name：执行/评估状态改判） */
export type ReviewFieldName = 'execution_status' | 'evaluation_status'

/** 人工复核留痕行（GET /tasks/results/{task_id}/review-history items 实测） */
export interface ReviewHistoryItem {
  id: number
  resultId: number
  taskId: number
  testCaseId: string
  fieldName: ReviewFieldName
  oldValue: string | null
  newValue: string | null
  comment: string
  createdByUserId: number | null
  createdAt: string | null
}

/** 复核提交载荷（POST /tasks/results/review；result_ids 单条=1 / 批量=n） */
export interface ReviewSubmitPayload {
  resultIds: number[]
  /** 执行状态改判（completed/failed/stopped/skipped） */
  executionStatus?: string
  /** 评估状态改判（completed/failed） */
  evaluationStatus?: string
  /** 复核备注（必填，min_length=1） */
  comment: string
}

/** 复核提交响应（backend reviewed/failed/review_count） */
export interface ReviewSubmitResult {
  reviewedCount: number
  /** 未生效条目（结果不存在/非终态/同值仅补备注） */
  failed: Array<{ resultId: number; message: string }>
}

/** 任务下已复核结果计数（GET /tasks/results/{task_id}/review-count） */
export interface ReviewCountData {
  reviewCount: number
}

/** 可改判执行状态全集（REVIEWABLE_EXECUTION_STATUSES 实测） */
export const REVIEWABLE_EXECUTION_STATUSES = [
  'completed',
  'failed',
  'stopped',
  'skipped',
] as const
export type ReviewableExecutionStatus =
  (typeof REVIEWABLE_EXECUTION_STATUSES)[number]

/** 可改判评估状态全集（REVIEWABLE_EVALUATION_STATUSES 双状态口径） */
export const REVIEWABLE_EVALUATION_STATUSES = [
  'completed',
  'failed',
] as const
export type ReviewableEvaluationStatus =
  (typeof REVIEWABLE_EVALUATION_STATUSES)[number]

/** 执行状态中文（§7 文案；V9.7.10 STATUS_LABELS 同源） */
export const EXECUTION_STATUS_LABELS: Record<string, string> = {
  completed: '已完成',
  failed: '执行失败',
  stopped: '已停止',
  skipped: '已跳过',
  pending: '排队中',
  queued: '排队中',
  running: '执行中',
}

/** 评估状态中文（双状态口径） */
export const EVALUATION_STATUS_LABELS: Record<string, string> = {
  completed: '已完成',
  failed: '评估失败',
  pending: '待评估',
  queued: '待评估',
  running: '评估中',
  calculating: '计算中',
  stopped: '已停止',
}

/** 任务/用例执行状态中文（状态点徽章展示，含未枚举回退原值） */
export function executionStatusLabel(status?: string | null): string {
  const s = status ?? ''
  return EXECUTION_STATUS_LABELS[s] ?? (s || '未知')
}

/** 任务/用例评估状态中文 */
export function evaluationStatusLabel(status?: string | null): string {
  const s = status ?? ''
  return EVALUATION_STATUS_LABELS[s] ?? (s || '未知')
}

// ---------------------------------------------------------------------------
// AI 复核（§5.3 契约定稿 INT-824；ai_reviews 表，infrastructure 层真实请求映射）
// ---------------------------------------------------------------------------

/** AI 复核结论（§2.1 状态机：待发起→执行中→已完成→已采纳/已驳回/待查） */
export type AiReviewVerdict = 'passed' | 'failed' | 'uncertain'
export type AiReviewPhase =
  | 'idle' // 待发起
  | 'running' // 执行中
  | 'completed' // 已完成（结论落位）
  | 'adopting' // 采纳中（落人工复核语义提交中）
  | 'adopted' // 已采纳（落人工复核语义）
  | 'rejected' // 已驳回
  | 'ignored' // 待查（忽略）

/** AI 复核任务状态（后端 ai_reviews.status：pending/running/completed/failed/canceled） */
export type AiReviewRecordStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'canceled'

/** AI 复核记录（ai_reviews 契约定稿 INT-824；由 infrastructure 真实请求映射） */
export interface AiReviewRecord {
  id: number
  resultId: number
  taskId: number
  testCaseId: string
  /** AI 复核任务状态（running=执行中 / completed=结论落位 / failed=执行失败） */
  status: AiReviewRecordStatus
  verdict: AiReviewVerdict
  /** 置信度 0-1（展示 {n}% 或高/中/低） */
  confidence: number
  reasoning: string
  adopted: boolean
  adoptedByUserId: number | null
  adoptedAt: string | null
  rejected: boolean
  rejectedByUserId: number | null
  rejectedAt: string | null
  createdAt: string
}

/** AI 发起请求（§5.3：result_ids + dimension_ids 可选） */
export interface AiReviewRequest {
  resultIds: number[]
  dimensionIds?: number[]
}

/** AI 采纳请求（INT-824 契约定稿：改判状态至少一项 + 备注必填；采纳落人工复核语义） */
export interface AiReviewAdoptPayload {
  /** 执行状态改判（completed/failed/stopped/skipped） */
  executionStatus?: string
  /** 评估状态改判（completed/failed） */
  evaluationStatus?: string
  /** 复核备注（必填，min_length=1；采纳预填 AI 理由后人工确认） */
  comment: string
}

/** AI 结论中文（§7：复核通过/复核不通过/存疑） */
export const AI_VERDICT_LABELS: Record<AiReviewVerdict, string> = {
  passed: '复核通过',
  failed: '复核不通过',
  uncertain: '存疑',
}

/** AI 结论徽章 variant（success=通过 / warning=不通过 / info=存疑） */
export const AI_VERDICT_VARIANTS: Record<
  AiReviewVerdict,
  'success' | 'warning' | 'info'
> = {
  passed: 'success',
  failed: 'warning',
  uncertain: 'info',
}

/** 置信度 → 展示（0-1 → 百分比；缺失显「—」） */
export function aiConfidenceLabel(confidence?: number | null): string {
  if (confidence === null || confidence === undefined || Number.isNaN(confidence)) {
    return '—'
  }
  return `${Math.round(confidence * 100)}%`
}

// ---------------------------------------------------------------------------
// 任务侧用例执行结果行（INT-795；GET /tasks/{taskId}/cases/{caseId}/results，复核弹窗结果摘要）
// ---------------------------------------------------------------------------

/** 用例执行结果行（任务侧复核消费；case results 行，INT-795） */
export interface CaseResultForReview {
  id: number
  deviceId: number | null
  deviceName: string | null
  apiId: number | null
  apiName: string | null
  executionStatus: string | null
  responseTime: number | null
  errorMessage: string | null
  reviewed: boolean
  reviewedByUserId: number | null
  reviewedAt: string | null
  lastReviewComment: string | null
  lastReviewAction: string | null
  reviewHistory: ReviewHistoryItem[]
  sourceTaskId: number
  sourceTaskName: string | null
}

/** 用例结果集合（GET /tasks/{taskId}/cases/{caseId}/results data，INT-795） */
export interface CaseResultsForReview {
  taskId: number
  caseId: string
  caseName: string
  results: CaseResultForReview[]
}

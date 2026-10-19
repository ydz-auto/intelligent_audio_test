/**
 * 人工审核 + AI 复核 领域模型 —— camelCase
 *
 * 对齐《19_人工审核与AI复核交互设计.md》§2.1 状态定义：
 * - 人工审核（权威层，落统计）：通过/驳回 + 原因 → 后端改判契约
 *   （execution_status completed/failed/stopped/skipped +
 *    evaluation_status completed/failed + comment 必填）
 * - AI 复核（建议层，不直接改统计）：待发起 → 执行中 → 已完成
 *   → 已采纳 / 已驳回 / 待查
 *
 * 后端接口：
 *   人工审核（INT-340）：POST /tasks/results/review、
 *     GET /tasks/results/{task_id}/review-count、GET /tasks/results/{task_id}/review-history
 *   AI 复核（INT-822/823/824）：POST /tasks/results/ai-review、
 *     GET /tasks/results/{task_id}/ai-review-history、
 *     POST /tasks/results/ai-review/{id}/adopt|reject
 */

/** 可改判执行状态（后端 REVIEWABLE_EXECUTION_STATUSES） */
export const REVIEWABLE_EXECUTION_STATUSES = ['completed', 'failed', 'stopped', 'skipped'] as const
/** 可改判评估状态（后端 REVIEWABLE_EVALUATION_STATUSES，双状态口径） */
export const REVIEWABLE_EVALUATION_STATUSES = ['completed', 'failed'] as const

/** 执行状态中文映射（改判 UI 展示） */
export const EXECUTION_STATUS_LABELS: Record<string, string> = {
  completed: '已完成',
  failed: '执行失败',
  stopped: '已停止',
  skipped: '已跳过',
  pending: '待执行',
  queued: '排队中',
  running: '执行中',
}

/** 评估状态中文映射（改判 UI 展示） */
export const EVALUATION_STATUS_LABELS: Record<string, string> = {
  completed: '已完成',
  failed: '评估失败',
  pending: '待评估',
  running: '评估中',
  calculating: '计算中',
  stopped: '已停止',
}

/** AI 复核状态（§2.1：待发起 → 执行中 → 已完成 → 已采纳/已驳回/待查） */
export type AiReviewPhase =
  | 'idle'           // 待发起（未发起过）
  | 'running'        // 执行中（异步复核中，可取消）
  | 'completed'      // 已完成（结论落位，待人工处置）
  | 'adopted'        // 已采纳（落人工复核语义，已提交改判）
  | 'rejected'       // 已驳回（保留原判定）
  | 'ignored'        // 待查（关闭暂不处理）

/** AI 复核结论判定（verdict） */
export type AiReviewVerdict = 'passed' | 'failed' | 'uncertain'

/** AI 复核任务状态（后端 ai_reviews.status：pending/running/completed/failed/canceled） */
export type AiReviewStatus = 'pending' | 'running' | 'completed' | 'failed' | 'canceled'

/** AI 复核结论中文映射 */
export const AI_REVIEW_VERDICT_LABELS: Record<AiReviewVerdict, string> = {
  passed: '复核通过',
  failed: '复核不通过',
  uncertain: '存疑',
}

/** AI 复核置信度（0-1 或高/中/低文本） */
export interface AiReviewConfidence {
  value: number
  label: '高' | '中' | '低'
}

/** AI 复核结论中文（null 安全，运行中/失败记录 verdict 为空时返回占位） */
export function aiVerdictLabel(verdict: AiReviewVerdict | null | undefined): string {
  return verdict ? AI_REVIEW_VERDICT_LABELS[verdict] : ''
}

/**
 * AI 复核记录（INT-862 契约对齐后端 AiReviewRecordDto / ai_reviews 表）。
 * 后端出参 snake_case 经 reviewAdapter.toAiReviewRecord 转 camelCase：
 * - status：复核任务状态（发起后 running，异步回写 verdict 后 completed，失败 failed）
 * - verdict/confidence：运行中未回写前为 null（界面仅在 completed 后展示结论）
 * - adopted/rejected：后端 0/1 → 领域 boolean
 * 原评估判定（originalEvaluationStatus）后端 DTO 不含，由消费面上下文提供。
 */
export interface AiReviewRecord {
  id: number
  resultId: number
  taskId: number
  testCaseId?: string | null
  dimensionId?: number | null
  dimensionName?: string | null
  status: AiReviewStatus
  verdict: AiReviewVerdict | null
  confidence: AiReviewConfidence | null
  reasoning: string
  adopted: boolean
  rejected: boolean
  createdAt: string
}

/** 报告侧复核统计徽章数据（§4.1 统计入口） */
export interface ReportReviewStats {
  /** 已复核结果条数（report_summaries.review_count 快照 / 来源任务 review-count） */
  reviewCount: number
  /** 用例级复核明细（test_case_id → 复核留痕，来自来源任务 review-history） */
  byCase: Map<string, ReviewHistoryItemDomain[]>
}

/** 复核留痕条目（camelCase；对齐 taskCaseDetail.ReviewHistoryItem 展示口径） */
export interface ReviewHistoryItemDomain {
  id?: number
  resultId?: number
  taskId?: number
  testCaseId?: string | null
  fieldName?: 'execution_status' | 'evaluation_status' | (string & {})
  oldValue?: string | null
  newValue?: string | null
  comment?: string | null
  createdByUserId?: number | null
  createdAt?: string | null
}

/** 人工复核提交载荷（POST /tasks/results/review） */
export interface ReviewSubmitPayload {
  resultIds: (string | number)[]
  executionStatus?: string
  evaluationStatus?: string
  comment: string
}

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
// AI 复核（契约定稿 INT-824；ai_reviews 表，infrastructure 层真实请求映射，INT-1063 去桩）
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

/** AI 复核任务状态（后端 ai_reviews.status：表 DEFAULT pending，实际 running/completed/failed；容错未知值） */
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
  /** AI 复核任务状态（pending/running=执行中 / completed=结论落位 / failed=执行失败；未知值容错展示） */
  status: AiReviewRecordStatus
  /** 复核维度 id（缺省=结果已完成评估的 LLM 判分维度） */
  dimensionId: number | null
  /** 结论（执行中/失败的记录无判定字段；消费侧仅在 completed 展示） */
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
  updatedAt: string | null
}

/** AI 发起请求（§5.3：result_ids + dimension_ids 可选 + force 重新复核） */
export interface AiReviewRequest {
  resultIds: number[]
  dimensionIds?: number[]
  /** 已有 AI 复核结论时重新复核（绕过幂等复用，§5.4） */
  force?: boolean
}

/**
 * INT-1279：用例评估维度 → AI 复核 dimension_ids。
 * 真实库（如任务 419）结果行无「已完成评估的 LLM 判分维度」（task_type_code 非 llm_judge），
 * 后端 dimension_ids 缺省口径查不到 → 发起 400。前端按用例评估维度显式传 dimension_ids
 * （TaskCaseBrief.evaluation_dimensions 为用例 config 评估维度快照），跳过缺省解析。
 * Number 归一（config 中 id 可为字符串）、非法/非正剔除；无维度 → undefined（走后端缺省）。
 */
export function toAiReviewDimensionIds(
  dims: Array<{ id: number | string; name: string }> | null | undefined
): number[] | undefined {
  const ids = (dims ?? [])
    .map((d) => Number(d?.id))
    .filter((n) => Number.isFinite(n) && n > 0)
  return ids.length > 0 ? ids : undefined
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

/** AI 复核任务状态中文（含未枚举回退原值；表 DEFAULT pending 容错） */
export const AI_REVIEW_STATUS_LABELS: Record<string, string> = {
  pending: '排队中',
  running: '复核中',
  completed: '已完成',
  failed: '失败',
  canceled: '已取消',
}

/** AI 复核任务状态中文（未知值回退原值，不抛错；§5.7 注记 2 容错口径） */
export function aiReviewStatusLabel(status?: string | null): string {
  const s = status ?? ''
  return AI_REVIEW_STATUS_LABELS[s] ?? (s || '未知')
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
/**
 * 结果行评估维度（GET /tasks/{taskId}/cases/{caseId}/results results[].dimensions）。
 * roundNumber：null=整体评估，0 起=第 (roundNumber+1) 轮（旧 Vue TestCaseDetailModal
 * metricsMap 同口径：`{name}@round:{rn+1}` / `{name}@overall`）。
 * dimensionType / parentDimension*（评分指标主/子层级，INT-2088）：后端 ACL 现不下发，
 * 适配器读到即透传（V9.7.10 comparisonData 同口径），读不到按主维度平铺。
 */
export interface CaseResultDimension {
  dimensionId: number | null
  name: string
  value: unknown
  score: number | null
  status: string | null
  evaluationStatus: string | null
  errorMessage: string | null
  roundNumber: number | null
  /** 主/子维度（缺省按 main 处理） */
  dimensionType?: string | null
  parentDimensionId?: number | null
  parentDimensionName?: string | null
}

export interface CaseResultForReview {
  id: number
  deviceId: number | null
  deviceName: string | null
  apiId: number | null
  apiName: string | null
  executionStatus: string | null
  responseTime: number | null
  errorMessage: string | null
  /** 结果行评估维度（INT-1688：用例详情弹窗设备×维度表数据源） */
  dimensions?: CaseResultDimension[]
  /** 设备侧 ASR 识别结果（旧 Vue asr_result 同源） */
  asrResult?: string | null
  /** 设备侧翻译结果 */
  translationResult?: string | null
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

// ---------------------------------------------------------------------------
// AI 复核会话上下文（19 规范 §5.3：灵犀Agent 复核会话预填契约）
// ---------------------------------------------------------------------------

/** 复核维度分数（设备×维度表，低分维度识别） */
export interface AiReviewDimensionScore {
  /** 维度名（@round:{n}/@overall 后缀已剥离） */
  name: string
  /** 平均分（多设备/多轮聚合；缺失 null） */
  score: number | null
}

/**
 * 复核上下文（19 §5.3：用例名/CaseId + 设备×结果 + 维度分数 + LLM 评语 +
 * 已有 ai_reviews 结论——现有端点聚合，无新后端）。作为灵犀Agent 复核会话的
 * 系统提示 + 首条 assistant 摘要卡输入；独立于全局主会话（19 §5.2）。
 */
export interface AiReviewContext {
  taskId: number
  caseId: string
  caseName: string
  /** 用例当前评估状态（GET /tasks/{id}/cases/{id}/detail；AI 判定 vs 原评估判定对比行） */
  evaluationStatus: string | null
  /** 设备×结果列表（GET /tasks/{id}/cases/{id}/results） */
  deviceResults: CaseResultForReview[]
  /** 评估维度分数（GET /tasks/{id}/cases/{id}/detail 设备×维度表聚合） */
  dimensionScores: AiReviewDimensionScore[]
  /** 现有复核/评语（results 行的 lastReviewComment；无则 null） */
  reasoning: string | null
  /** 已有 ai_reviews 结论（GET /tasks/results/{task_id}/ai-review-history，按 testCaseId 过滤） */
  existingReviews: AiReviewRecord[]
}

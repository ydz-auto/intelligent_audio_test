// -*- coding: utf-8 -*-
/**
 * AI 复核 API（19 规范 §5.2/§5.3，INT-796）——建议层，不直接改统计。
 *
 * 真实接口（后端已具备，INT-762 审计对位）：
 *   POST /tasks/results/review（人工复核提交，人工「采纳」AI 结论时复用）
 *   GET  /tasks/results/{task_id}/review-count / review-history（任务复核统计/历史）
 *
 * AI 复核端点（§8-2 契约建议）后端未立项（FEAT INT-800 已 done，待合入 V9.7.31 常驻栈）
 * → 本层留桩返回符合 §5.3 契约形态的示例，代码标 `// 待接线`；立项合入后替换为真实请求。
 */

export type AiReviewVerdict = 'passed' | 'failed' | 'uncertain'

/** AI 复核记录（§5.3 契约建议） */
export interface AiReviewRecord {
  id: number
  resultId: number
  taskId: number
  testCaseId: string
  verdict: AiReviewVerdict
  confidence: number
  reasoning: string
  adopted: boolean
  rejected: boolean
  createdAt: string
}

/** AI 复核发起载荷（result_ids + 可选复核维度） */
export interface AiReviewRequest {
  resultIds: number[]
  dimensionIds?: number[]
}

export type AiReviewPhase = 'idle' | 'running' | 'completed' | 'adopted' | 'rejected'

/** AI 结论中文（§7 文案） */
export const AI_VERDICT_LABELS: Record<AiReviewVerdict, string> = {
  passed: '复核通过',
  failed: '复核不通过',
  uncertain: '存疑',
}

/** 置信度展示（§4.3：{n}% 或高/中/低） */
export function aiConfidenceLabel(confidence: number): string {
  if (confidence >= 0.8) return '高'
  if (confidence >= 0.55) return '中'
  return '低'
}

// ---------------------------------------------------------------------------
// AI 复核桩存储（会话级内存）；FEAT INT-800 合入后删除并由后端读写替代
// ---------------------------------------------------------------------------

const _aiReviewStore = new Map<number, AiReviewRecord>()
let _aiReviewSeq = 1000

/** 桩：确定性结论（result_id 派生，避免纯随机难复现；契约建议 §5.3） */
function _stubVerdict(resultId: number): AiReviewVerdict {
  const n = resultId % 10
  if (n < 4) return 'passed'
  if (n < 8) return 'uncertain'
  return 'failed'
}

/** 桩：理由模板（§7 文案：AI 判定 vs 原评估判定；低分/失败/断言不符复检） */
function _stubReasoning(verdict: AiReviewVerdict): string {
  const base = '大模型对当前评估结果进行复检：综合判分数据与语音特征一致性，'
  if (verdict === 'passed') {
    return `${base}未发现与低分判定相符的明显异常，建议维持原评估结论。`
  }
  if (verdict === 'failed') {
    return `${base}发现语音内容与参考文本偏差显著，建议按评估失败处理。`
  }
  return `${base}存在多处临界特征，无法给出明确判定，建议人工复核确认。`
}

/** 发起 AI 复核（POST /tasks/results/ai-review 契约建议；待接线） */
export async function requestAiReview(
  taskId: number,
  caseId: string,
  payload: AiReviewRequest,
): Promise<AiReviewRecord> {
  // 待接线：FEAT INT-800 合入后替换为 request('POST', '/tasks/results/ai-review', { result_ids, dimension_ids })
  const resultId = payload.resultIds[0] ?? 0
  const verdict = _stubVerdict(resultId)
  const record: AiReviewRecord = {
    id: _aiReviewSeq++,
    resultId,
    taskId,
    testCaseId: caseId,
    verdict,
    confidence: verdict === 'uncertain' ? 0.5 : 0.85,
    reasoning: _stubReasoning(verdict),
    adopted: false,
    rejected: false,
    createdAt: new Date().toISOString(),
  }
  _aiReviewStore.set(record.id, record)
  return record
}

/** AI 复核历史（GET /tasks/results/{task_id}/ai-review-history 契约建议；待接线） */
export async function fetchAiReviewHistory(taskId: number): Promise<AiReviewRecord[]> {
  // 待接线：FEAT INT-800 合入后替换为真实 GET；当前返回会话内桩记录
  return [..._aiReviewStore.values()].filter((r) => r.taskId === taskId)
}

/** 采纳 AI 结论（POST /tasks/results/ai-review/{id}/adopt 契约建议；待接线） */
export async function adoptAiReview(recordId: number): Promise<AiReviewRecord> {
  // 待接线：FEAT INT-800 合入后替换为真实 POST；采纳后落人工复核语义由前端调 submitReview 完成
  const record = _aiReviewStore.get(recordId)
  if (!record) throw new Error('AI 复核记录不存在')
  record.adopted = true
  record.rejected = false
  _aiReviewStore.set(recordId, record)
  return record
}

/** 驳回 AI 结论（POST /tasks/results/ai-review/{id}/reject 契约建议；待接线） */
export async function rejectAiReview(recordId: number): Promise<AiReviewRecord> {
  // 待接线：FEAT INT-800 合入后替换为真实 POST；驳回保留原判定，记录标记已驳回备查
  const record = _aiReviewStore.get(recordId)
  if (!record) throw new Error('AI 复核记录不存在')
  record.rejected = true
  record.adopted = false
  _aiReviewStore.set(recordId, record)
  return record
}

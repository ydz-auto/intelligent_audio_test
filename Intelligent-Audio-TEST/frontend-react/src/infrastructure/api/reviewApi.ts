/**
 * 人工复核 + AI 复核 API（infrastructure/api，19_人工审核与AI复核交互设计.md §3.6/§4.4，INT-793）。
 * 真实接口（经 client.ts 统一信封解包）：
 *   POST /api/v1/tasks/results/review            （提交复核，task.result.review）
 *   GET  /api/v1/tasks/results/{task_id}/review-count  （已复核条数，task:read）
 *   GET  /api/v1/tasks/results/{task_id}/review-history（复核历史，task:read）
 *   GET  /api/v1/tasks/{task_id}/cases/{case_id}/results（用例执行结果：result_id/复核标注）
 * AI 复核端点（发起/历史/采纳/驳回）后端未立项（§8-2）→ 本层留桩返回契约形态样例，代码标
 * `// 待接线`；立项后替换为真实请求（FEAT INT-xxx）。
 */
import type {
  AiReviewRecord,
  AiReviewRequest,
  CaseResultsForReview,
  ReviewHistoryItem,
  ReviewSubmitPayload,
  ReviewSubmitResult,
} from '@/domain/models/review'
import type {
  AiReviewRecordDto,
  CaseResultsDataDto,
  ReviewCountDto,
  ReviewHistoryDataDto,
  ReviewSubmitResponseDto,
} from '@/infrastructure/dto/review.dto'
import {
  toAiReviewHistoryList,
  toAiReviewRecord,
  toCaseResultsForReview,
  toReviewHistoryList,
  toReviewSubmitResult,
} from '@/infrastructure/adapters/reviewAdapter'
import { request } from './client'

/** 提交复核（单条/批量逐条留痕；comment 必填） */
export async function submitReview(
  payload: ReviewSubmitPayload
): Promise<ReviewSubmitResult> {
  const dto = await request<ReviewSubmitResponseDto>(
    'POST',
    '/tasks/results/review',
    {
      result_ids: payload.resultIds,
      execution_status: payload.executionStatus || undefined,
      evaluation_status: payload.evaluationStatus || undefined,
      comment: payload.comment,
    }
  )
  return toReviewSubmitResult(dto)
}

/** 任务已复核结果计数（覆盖提醒 / 报告头统计徽章） */
export async function fetchReviewCount(taskId: number): Promise<number> {
  const dto = await request<ReviewCountDto>(
    'GET',
    `/tasks/results/${taskId}/review-count`
  )
  return dto.review_count ?? 0
}

/** 任务复核历史（多次复核追加不覆盖，时间倒序由消费侧排） */
export async function fetchReviewHistory(
  taskId: number
): Promise<ReviewHistoryItem[]> {
  const dto = await request<ReviewHistoryDataDto>(
    'GET',
    `/tasks/results/${taskId}/review-history`
  )
  return toReviewHistoryList(dto.items ?? [])
}

/** 用例执行结果（复核入口溯源：result_id + 复核标注 + 设备/API 名；task:read） */
export async function fetchCaseResults(
  taskId: number,
  caseId: string
): Promise<CaseResultsForReview> {
  const dto = await request<CaseResultsDataDto>(
    'GET',
    `/tasks/${taskId}/cases/${caseId}/results`
  )
  return toCaseResultsForReview(dto)
}

// ---------------------------------------------------------------------------
// AI 复核（§5.3 契约建议；后端未立项 → 留桩 `// 待接线`）
// ---------------------------------------------------------------------------

/** 桩存储（会话级内存）：AI 复核记录，FEAT 立项后删除并由后端读写替代 */
const _aiReviewStore = new Map<number, AiReviewRecordDto>()
let _aiReviewSeq = 1000

/** 桩：确定性结论（result_id 派生，避免纯随机难复现；契约建议 §5.3） */
function _stubVerdict(resultId: number): AiReviewRecordDto['verdict'] {
  const n = resultId % 10
  if (n < 4) return 'passed'
  if (n < 8) return 'uncertain'
  return 'failed'
}

/** 桩：理由模板（§7 文案：AI 判定 vs 原评估判定；低分/失败/断言不符复检） */
function _stubReasoning(verdict: AiReviewRecordDto['verdict']): string {
  const base =
    '大模型对当前评估结果进行复检：综合判分数据与语音特征一致性，'
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
  payload: AiReviewRequest
): Promise<AiReviewRecord> {
  // 待接线：FEAT 立项后替换为 request('POST', '/tasks/results/ai-review', ...)
  const resultId = payload.resultIds[0]
  const verdict = _stubVerdict(resultId)
  const now = new Date().toISOString()
  const record: AiReviewRecordDto = {
    id: _aiReviewSeq++,
    result_id: resultId,
    task_id: taskId,
    test_case_id: caseId,
    verdict,
    confidence: verdict === 'uncertain' ? 0.5 : 0.85,
    reasoning: _stubReasoning(verdict),
    adopted: false,
    adopted_by_user_id: null,
    adopted_at: null,
    rejected: false,
    created_at: now,
  }
  _aiReviewStore.set(record.id, record)
  return toAiReviewRecord(record)
}

/** AI 复核历史（GET /tasks/results/{task_id}/ai-review-history 契约建议；待接线） */
export async function fetchAiReviewHistory(
  taskId: number
): Promise<AiReviewRecord[]> {
  // 待接线：FEAT 立项后替换为真实 GET；当前返回会话内桩记录
  const items = [..._aiReviewStore.values()].filter(
    (r) => r.task_id === taskId
  )
  return toAiReviewHistoryList(items)
}

/** 采纳 AI 结论（POST /tasks/results/ai-review/{id}/adopt 契约建议；待接线） */
export async function adoptAiReview(
  recordId: number
): Promise<AiReviewRecord> {
  // 待接线：FEAT 立项后替换为真实 POST；采纳后落人工复核语义由前端调 submitReview 完成
  const record = _aiReviewStore.get(recordId)
  if (!record) {
    throw new Error('AI 复核记录不存在')
  }
  record.adopted = true
  record.rejected = false
  _aiReviewStore.set(recordId, record)
  return toAiReviewRecord(record)
}

/** 驳回 AI 结论（POST /tasks/results/ai-review/{id}/reject 契约建议；待接线） */
export async function rejectAiReview(recordId: number): Promise<AiReviewRecord> {
  // 待接线：FEAT 立项后替换为真实 POST；驳回保留原判定，记录标记已驳回备查
  const record = _aiReviewStore.get(recordId)
  if (!record) {
    throw new Error('AI 复核记录不存在')
  }
  record.rejected = true
  record.adopted = false
  _aiReviewStore.set(recordId, record)
  return toAiReviewRecord(record)
}

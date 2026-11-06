/**
 * reviewApi AI 复核四桩接真实请求单测（接线卡 INT-825）：
 * requestAiReview POST /tasks/results/ai-review / fetchAiReviewHistory GET 历史 /
 * adoptAiReview POST adopt（携带复核载荷）/ rejectAiReview POST reject。
 * 统一 mock 全局 fetch（client.ts 依赖），断言 URL、请求体 snake_case 契约与
 * 统一信封解包 → camelCase 领域。adopt 无载荷 → ApiError。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  API_BASE_URL,
  setSessionExpiredHandler,
} from '@/infrastructure/api/client'
import {
  adoptAiReview,
  fetchAiReviewHistory,
  rejectAiReview,
  requestAiReview,
} from '@/infrastructure/api/reviewApi'
import type { AiReviewRecordDto } from '@/infrastructure/dto/review.dto'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function okEnvelope(data: unknown): Response {
  return jsonResponse({ success: true, code: 0, message: 'ok', data })
}

function completedRecord(resultId: number, id = 1001): AiReviewRecordDto {
  return {
    id,
    result_id: resultId,
    task_id: 407,
    test_case_id: '86756aa2-2c97-4548-b493-b2312b20a8c4',
    dimension_id: 21,
    status: 'completed',
    verdict: 'passed',
    confidence: 0.85,
    reasoning: '大模型复检建议维持原评估结论',
    adopted: 0,
    adopted_by_user_id: null,
    adopted_at: null,
    rejected: 0,
    rejected_by_user_id: null,
    rejected_at: null,
    created_at: '2026-10-19T04:00:00',
    updated_at: '2026-10-19T04:00:00',
  }
}

describe('reviewApi AI 复核四端点', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
    authTokenStore.clear()
    setSessionExpiredHandler(null)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    authTokenStore.clear()
    setSessionExpiredHandler(null)
  })

  it('requestAiReview：POST /tasks/results/ai-review，result_ids 透传 → 返回首条记录', async () => {
    fetchMock.mockResolvedValue(
      okEnvelope({
        items: [completedRecord(4690)],
        reused: false,
        skipped: [],
      })
    )
    const record = await requestAiReview(407, 'case-x', { resultIds: [4690] })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE_URL}/tasks/results/ai-review`)
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ result_ids: [4690] })
    expect(record).toMatchObject({
      id: 1001,
      resultId: 4690,
      taskId: 407,
      status: 'completed',
      verdict: 'passed',
      confidence: 0.85,
    })
  })

  it('requestAiReview：dimensionIds 缺省不发送；skipped 无记录 → ApiError', async () => {
    fetchMock.mockResolvedValue(
      okEnvelope({ items: [], reused: false, skipped: [{ result_id: 1, message: '结果不存在' }] })
    )
    await expect(
      requestAiReview(407, 'case-x', { resultIds: [1], dimensionIds: [21] })
    ).rejects.toThrow('结果不存在')
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string)).toEqual({
      result_ids: [1],
      dimension_ids: [21],
    })
  })

  it('fetchAiReviewHistory：GET 历史并透传 result_id/status 过滤参数', async () => {
    fetchMock.mockResolvedValue(okEnvelope({ items: [completedRecord(4690)] }))
    const records = await fetchAiReviewHistory(407, {
      resultId: 4690,
      status: 'completed',
    })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(
      `${API_BASE_URL}/tasks/results/407/ai-review-history?result_id=4690&status=completed`
    )
    expect(init.method).toBe('GET')
    expect(records).toHaveLength(1)
    expect(records[0].resultId).toBe(4690)
  })

  it('adoptAiReview：POST adopt 携带复核载荷（evaluation_status + comment）→ 返回采纳后记录', async () => {
    const adopted = completedRecord(4690, 1002)
    adopted.adopted = 1
    adopted.adopted_by_user_id = 7
    adopted.adopted_at = '2026-10-19T04:05:00'
    fetchMock.mockResolvedValue(okEnvelope({ item: adopted, applied: [] }))
    const record = await adoptAiReview(1002, {
      evaluationStatus: 'completed',
      comment: '采纳 AI 复核结论',
    })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE_URL}/tasks/results/ai-review/1002/adopt`)
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({
      evaluation_status: 'completed',
      comment: '采纳 AI 复核结论',
    })
    expect(record.adopted).toBe(true)
    expect(record.adoptedByUserId).toBe(7)
  })

  it('adoptAiReview：无复核载荷 → 抛错（消费侧需携带载荷，契约要求备注必填）', async () => {
    await expect(adoptAiReview(1002)).rejects.toThrow(
      '采纳 AI 复核结论需携带复核载荷'
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('rejectAiReview：POST reject 空体 → 返回驳回标记记录', async () => {
    const rejected = completedRecord(4690, 1003)
    rejected.rejected = 1
    rejected.rejected_by_user_id = 7
    rejected.rejected_at = '2026-10-19T04:06:00'
    fetchMock.mockResolvedValue(okEnvelope(rejected))
    const record = await rejectAiReview(1003)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE_URL}/tasks/results/ai-review/1003/reject`)
    expect(init.method).toBe('POST')
    expect(record.rejected).toBe(true)
    expect(record.rejectedByUserId).toBe(7)
  })
})

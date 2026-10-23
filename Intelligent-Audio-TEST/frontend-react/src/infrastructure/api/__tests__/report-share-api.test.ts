/**
 * 报告分享 API 单测（INT-1408 接线：INT-971 端点 DTO 映射）。
 * createReportShare：POST /reports/{id}/share 请求体（recipients 逗号分隔字符串、
 * custom 附 expires_at）→ {token, shareUrl, visits, lastVisitedAt}，shareUrl origin 归一化到前端；
 * revokeReportShare：DELETE /reports/{id}/share/{token}；
 * fetchReportShareStats：GET /reports/{id}/share 列表定位 token 回读访问统计。
 * 统一 mock 全局 fetch（照 reports-log-files.test.ts 先例）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL } from '@/infrastructure/api/client'
import {
  createReportShare,
  fetchReportShareStats,
  revokeReportShare,
} from '@/infrastructure/api/report-share-api'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function envelope(data: unknown) {
  return { success: true, code: 0, message: 'Success', data }
}

describe('报告分享 API（INT-1408 接线）', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
    authTokenStore.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    authTokenStore.clear()
  })

  it('createReportShare：POST /reports/{id}/share，public 时 recipients 传空串，DTO → 域模型', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        envelope({
          token: 'tk-abc',
          access: 'public',
          expires_at: null,
          password_set: false,
          recipients: [],
          visits: 0,
          last_visited_at: null,
          share_url: `http://localhost:15000/report/42?share=tk-abc`,
        })
      )
    )

    const info = await createReportShare({
      reportId: 42,
      access: 'public',
      expiry: 'none',
      password: '',
      recipients: '',
    })

    // 请求形态
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`${API_BASE_URL}/reports/42/share`)
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({
      access: 'public',
      expiry: 'none',
      password: '',
      recipients: '',
    })

    // 域模型映射
    expect(info.token).toBe('tk-abc')
    expect(info.visits).toBe(0)
    expect(info.lastVisitedAt).toBeNull()
    expect(info.expiresAt).toBeNull()
    // share_url origin 归一化到当前前端 origin（保留 path+query）
    expect(info.shareUrl).toBe(`${window.location.origin}/report/42?share=tk-abc`)
  })

  it('createReportShare：specific 透传 recipients、custom 附 expires_at，share_url 缺失时按前端路由形态兜底', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        envelope({
          token: 'tk-xyz',
          access: 'specific',
          expires_at: '2030-01-01T00:00:00Z',
          password_set: false,
          recipients: [],
          visits: 0,
          last_visited_at: null,
        })
      )
    )

    const info = await createReportShare({
      reportId: 7,
      access: 'specific',
      expiry: 'custom',
      expiresAt: '2030-01-01T00:00:00Z',
      password: 'pw',
      recipients: 'alice,bob@example.com',
    })

    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse(init.body)).toEqual({
      access: 'specific',
      expiry: 'custom',
      expires_at: '2030-01-01T00:00:00Z',
      password: 'pw',
      recipients: 'alice,bob@example.com',
    })
    expect(info.shareUrl).toBe(`${window.location.origin}/report/7?share=tk-xyz`)
    expect(info.expiresAt).toBe('2030-01-01T00:00:00Z')
  })

  it('revokeReportShare：DELETE /reports/{id}/share/{token}', async () => {
    fetchMock.mockResolvedValue(jsonResponse(envelope({ revoked: true })))

    await revokeReportShare(42, 'tk-abc')

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`${API_BASE_URL}/reports/42/share/tk-abc`)
    expect(init.method).toBe('DELETE')
  })

  it('fetchReportShareStats：GET 列表定位 token 回读 visits/last_visited_at', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        envelope({
          shares: [
            {
              token: 'tk-other',
              access: 'public',
              expires_at: null,
              password_set: false,
              recipients: [],
              visits: 5,
              last_visited_at: null,
              revoked: false,
              created_at: '2026-10-20T00:00:00+08:00',
            },
            {
              token: 'tk-abc',
              access: 'public',
              expires_at: null,
              password_set: false,
              recipients: [],
              visits: 3,
              last_visited_at: '2026-10-21T01:02:03+08:00',
              revoked: false,
              created_at: '2026-10-20T00:00:00+08:00',
            },
          ],
        })
      )
    )

    const stat = await fetchReportShareStats(42, 'tk-abc')

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`${API_BASE_URL}/reports/42/share`)
    expect(init.method).toBe('GET')
    expect(stat).toEqual({ visits: 3, lastVisitedAt: '2026-10-21T01:02:03+08:00' })
  })

  it('fetchReportShareStats：token 不在列表（已撤销等）→ 归零', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(envelope({ shares: [{ token: 'tk-other', visits: 2 }] }))
    )

    const stat = await fetchReportShareStats(42, 'tk-gone')
    expect(stat).toEqual({ visits: 0, lastVisitedAt: null })
  })
})

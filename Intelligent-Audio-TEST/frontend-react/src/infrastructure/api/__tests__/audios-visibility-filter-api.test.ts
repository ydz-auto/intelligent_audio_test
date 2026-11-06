/**
 * INT-2197 音频可见性筛选契约：fetchAudios（POST /audios）服务端参数 visibility。
 * shared/private 原样下发；未选（null/空）不发送该键（后端按「全部」处理，含 admin 全量）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL, setSessionExpiredHandler } from '@/infrastructure/api/client'
import { fetchAudios } from '@/infrastructure/api/audios-api'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function listResponse(total: number): Response {
  return jsonResponse({
    success: true,
    code: 0,
    data: {
      items: [],
      total,
      page: 1,
      per_page: 20,
      pages: Math.ceil(total / 20),
      stats: {
        total_files: total,
        total_size: '0 B',
        total_duration: '0:00',
        today_uploads: 0,
      },
    },
  })
}

function bodyOfCall(): Record<string, unknown> {
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
  return JSON.parse(String(init.body)) as Record<string, unknown>
}

describe('fetchAudios 可见性筛选契约（INT-2197）', () => {
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

  it('visibility=shared：请求体带 visibility，total 取服务端返回', async () => {
    fetchMock.mockResolvedValue(listResponse(1957))
    const result = await fetchAudios({ visibility: 'shared' })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE_URL}/audios`)
    expect(init.method).toBe('POST')
    expect(bodyOfCall()).toEqual({
      page: 1,
      per_page: 20,
      visibility: 'shared',
    })
    expect(result.total).toBe(1957)
  })

  it('visibility=private：请求体带 visibility，空结果 total=0 由服务端给出', async () => {
    fetchMock.mockResolvedValue(listResponse(0))
    const result = await fetchAudios({ visibility: 'private' })

    expect(bodyOfCall().visibility).toBe('private')
    expect(result.total).toBe(0)
  })

  it('未选可见性（不传/null）不发送 visibility 键', async () => {
    fetchMock.mockResolvedValue(listResponse(1957))
    await fetchAudios({})

    expect(bodyOfCall()).not.toHaveProperty('visibility')
  })

  it('可见性与其他筛选一并下发（服务端组合过滤，不是前端过滤）', async () => {
    fetchMock.mockResolvedValue(listResponse(12))
    await fetchAudios({ keyword: '测试', visibility: 'private', page: 2 })

    expect(bodyOfCall()).toEqual({
      page: 2,
      per_page: 20,
      keyword: '测试',
      visibility: 'private',
    })
  })
})

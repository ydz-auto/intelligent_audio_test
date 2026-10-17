/**
 * userApi.updateUser P3-1 单测（INT-681）：编辑态 PUT /auth/users/{id} 不含 display_name。
 * 后端 update_user 无 displayName 字段（DTO 兜底 username），前端编辑态将「显示名」置灰
 * 且 updateUser 不发送该字段。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { updateUser } from '@/infrastructure/api/userApi'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('userApi.updateUser 不发送 display_name（P3-1）', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('PUT 请求体仅含 email/status，不含 display_name/displayName', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ success: true, code: 0, data: null })
    )

    await updateUser('123', {
      displayName: '改名尝试',
      email: 'new@example.com',
      status: 'disabled',
    })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/auth/users/123')
    expect(String(init.method).toUpperCase()).toBe('PUT')
    const body = JSON.parse(String(init.body)) as Record<string, unknown>
    expect(body).toEqual({ email: 'new@example.com', status: 'inactive' })
    expect('display_name' in body).toBe(false)
    expect('displayName' in body).toBe(false)
  })
})

/**
 * userApi.updateUser 显示名接线单测（INT-698）：后端 display_name 落地后，
 * 编辑态 PUT /auth/users/{id} 在 patch.displayName 已定义时携带 display_name；
 * 未定义（编辑态未改显示名）时不发送该键，保留后端原值。
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

describe('userApi.updateUser 显示名接线（INT-698）', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('patch.displayName 已定义时 PUT 请求体携带 display_name（并含 email/status）', async () => {
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
    expect(body).toEqual({
      display_name: '改名尝试',
      email: 'new@example.com',
      status: 'inactive',
    })
  })

  it('patch.displayName 未定义时 PUT 请求体不含 display_name（保留后端原值）', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ success: true, code: 0, data: null })
    )

    await updateUser('123', { email: 'other@example.com' })

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const body = JSON.parse(String(init.body)) as Record<string, unknown>
    expect(body).toEqual({ email: 'other@example.com' })
    expect('display_name' in body).toBe(false)
    expect('displayName' in body).toBe(false)
  })

  it('patch.displayName 显式传空串时清空（display_name 为空）', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ success: true, code: 0, data: null })
    )

    await updateUser('123', { displayName: '' })

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const body = JSON.parse(String(init.body)) as Record<string, unknown>
    expect(body).toEqual({ display_name: '' })
  })
})

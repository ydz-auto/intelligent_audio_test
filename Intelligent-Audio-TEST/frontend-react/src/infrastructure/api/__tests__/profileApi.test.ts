/**
 * profileApi / favoritesApi 真实接口单测（接线 INT-650）：
 * listOAuthBindings snake→camel 映射 / completeOAuthBinding POST 请求体 /
 * unbindOAuthBinding DELETE 路径 / getFavorites 三数组 length 计数映射。
 * fetch mock 依序消费；token 注入与 401 语义由 client 拦截器（client.test.ts）覆盖。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL } from '@/infrastructure/api/client'
import { getFavorites } from '@/infrastructure/api/favoritesApi'
import {
  completeOAuthBinding,
  listOAuthBindings,
  unbindOAuthBinding,
} from '@/infrastructure/api/profileApi'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 依序消费的 fetch mock */
function queueResponses(...responses: Response[]): void {
  fetchMock.mockImplementation(() => {
    const next = responses.shift()
    if (!next) throw new Error('fetch 调用超出 mock 队列')
    return Promise.resolve(next)
  })
}

describe('profileApi / favoritesApi 真实接口', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
    authTokenStore.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('listOAuthBindings：GET /auth/oauth/bindings → provider_id 数值转字符串', async () => {
    queueResponses(
      jsonResponse({
        success: true,
        code: 0,
        data: {
          bindings: [
            {
              provider_id: 1,
              provider_name: 'GitHub',
              provider_slug: 'github',
              provider_icon: 'github',
              provider_user_id: 'octocat-2026',
            },
          ],
        },
      })
    )

    const bindings = await listOAuthBindings()

    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE_URL}/auth/oauth/bindings`,
      expect.objectContaining({ method: 'GET' })
    )
    expect(bindings).toEqual([
      {
        providerId: '1',
        providerName: 'GitHub',
        providerSlug: 'github',
        providerIcon: 'github',
        providerUserId: 'octocat-2026',
      },
    ])
  })

  it('completeOAuthBinding：POST /auth/oauth/bindings 携 bind_ticket JSON body', async () => {
    queueResponses(
      jsonResponse({ success: true, code: 0, message: '绑定成功', data: null })
    )

    await completeOAuthBinding('ticket-abc')

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`${API_BASE_URL}/auth/oauth/bindings`)
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ bind_ticket: 'ticket-abc' })
  })

  it('completeOAuthBinding：空票据前端护栏抛错，不发请求', async () => {
    await expect(completeOAuthBinding('  ')).rejects.toThrow('绑定票据为空')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('unbindOAuthBinding：DELETE /auth/oauth/bindings/{provider_id}', async () => {
    queueResponses(
      jsonResponse({ success: true, code: 0, message: '解绑成功', data: null })
    )

    await unbindOAuthBinding('3')

    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE_URL}/auth/oauth/bindings/3`,
      expect.objectContaining({ method: 'DELETE' })
    )
  })

  it('getFavorites：GET /favorites 三数组 length → 三类计数', async () => {
    queueResponses(
      jsonResponse({
        success: true,
        code: 0,
        data: {
          task: ['T-1'],
          report: [],
          testcase: ['TC-1', 'TC-2'],
        },
      })
    )

    const counts = await getFavorites()

    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE_URL}/favorites`,
      expect.objectContaining({ method: 'GET' })
    )
    expect(counts).toEqual({ task: 1, report: 0, testcase: 2 })
  })

  it('getFavorites：data 缺省数组兜底为 0', async () => {
    queueResponses(
      jsonResponse({ success: true, code: 0, data: { task: [], report: null, testcase: undefined } })
    )

    expect(await getFavorites()).toEqual({ task: 0, report: 0, testcase: 0 })
  })
})

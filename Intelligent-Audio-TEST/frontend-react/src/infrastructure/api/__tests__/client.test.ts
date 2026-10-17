/**
 * client.ts 统一 fetch 封装单测（接线基座 INT-605）。
 * 覆盖：baseURL/query 拼接、JWT token 注入、统一信封解包、错误码映射、
 * 401 skipAuthRedirect 特例、401 refresh 成功重试/失败会话过期、网络失败文案。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/infrastructure/api/api-error'
import {
  API_BASE_URL,
  onSessionExpired,
  request,
  setSessionExpiredHandler,
} from '@/infrastructure/api/client'
import { ApiErrorCode } from '@/domain/models/api'
import { NETWORK_FAILED_COPY } from '@/domain/models/auth'
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

describe('client 统一 fetch 封装', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    authTokenStore.clear()
    fetchMock.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    authTokenStore.clear()
  })

  it('GET 拼接 baseURL 与 query 参数，自动注入 Bearer token', async () => {
    authTokenStore.set('jwt-token-1')
    queueResponses(jsonResponse({ success: true, code: 0, data: { ok: 1 } }))

    await request<{ ok: number }>('GET', '/testcases', undefined, {
      params: { page: 1, keyword: '音频', empty: undefined, nil: null },
    })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE_URL}/testcases?page=1&keyword=%E9%9F%B3%E9%A2%91`)
    const headers = init.headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer jwt-token-1')
    expect(headers.Accept).toBe('application/json')
  })

  it('basePath=/api 覆盖前缀：根级 /api/status（INT-672）', async () => {
    queueResponses(
      jsonResponse({ api_base_url: 'http://localhost:5000', server_address: '::1' })
    )
    await request('GET', '/status', undefined, { basePath: '/api' })
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe('/api/status')
  })

  it("basePath='' 覆盖前缀：根路径 /health（INT-672）", async () => {
    queueResponses(jsonResponse({ status: 'ok', service: 'api_gateway' }))
    await request('GET', '/health', undefined, { basePath: '' })
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe('/health')
  })

  it('basePath 覆盖同样走 query 拼接与 Bearer 注入（INT-672）', async () => {
    authTokenStore.set('jwt-token-1')
    queueResponses(jsonResponse({ success: true, code: 0, data: null }))
    await request('GET', '/option/', undefined, { basePath: '/api', params: { key: 'x' } })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/option/?key=x')
    const headers = init.headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer jwt-token-1')
  })

  it('未传 basePath 时沿用默认 /api/v1（回归：auth/home/tasks URL 不变）', async () => {
    queueResponses(
      jsonResponse({ success: true, code: 0, data: { ok: 1 } }),
      jsonResponse({ success: true, code: 0, data: { saved: true } })
    )
    await request('GET', '/home/stats')
    await request('POST', '/tasks', { name: 't' })
    expect(fetchMock.mock.calls[0][0]).toBe(`${API_BASE_URL}/home/stats`)
    expect(fetchMock.mock.calls[1][0]).toBe(`${API_BASE_URL}/tasks`)
  })

  it('统一信封解包：{ code, message, data } → data', async () => {
    queueResponses(
      jsonResponse({ success: true, code: 0, message: 'Success', data: { id: 7 } })
    )
    const data = await request<{ id: number }>('GET', '/home/stats')
    expect(data).toEqual({ id: 7 })
  })

  it('无信封响应（登录回包）原样返回', async () => {
    queueResponses(jsonResponse({ access_token: 't', token_type: 'Bearer' }))
    const data = await request<{ access_token: string }>('GET', '/auth/mode')
    expect(data).toEqual({ access_token: 't', token_type: 'Bearer' })
  })

  it('POST 对象 body 序列化 JSON 且带 Content-Type', async () => {
    queueResponses(jsonResponse({ success: true, code: 0, data: { saved: true } }))
    await request('POST', '/groups', { name: '组A' })
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = init.headers as Record<string, string>
    expect(headers['Content-Type']).toBe('application/json')
    expect(init.body).toBe(JSON.stringify({ name: '组A' }))
  })

  it('formUrlEncoded 以表单编码提交（登录 Form 契约）', async () => {
    queueResponses(jsonResponse({ success: true, code: 0, data: null }))
    await request('POST', '/auth/login', { username: 'u', password: 'p' }, {
      formUrlEncoded: true,
    })
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = init.headers as Record<string, string>
    expect(headers['Content-Type']).toBe('application/x-www-form-urlencoded')
    // fetch 对 URLSearchParams 自动序列化为 username=u&password=p
    expect(init.body).toBeInstanceOf(URLSearchParams)
    const params = init.body as URLSearchParams
    expect(params.get('username')).toBe('u')
    expect(params.get('password')).toBe('p')
  })

  it('错误码映射：HTTP 400 + 业务码 203 → ApiError 带枚举 code 与中文文案', async () => {
    queueResponses(
      jsonResponse(
        { success: false, code: 203, message: '', detail: '细节' },
        400
      )
    )
    const error = await request('GET', '/tasks').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    const apiError = error as ApiError
    expect(apiError.code).toBe(ApiErrorCode.OPERATION_FAILED)
    expect(apiError.httpStatus).toBe(400)
    expect(apiError.userMessage).toBe('操作失败，请稍后重试')
  })

  it('错误码映射：106 凭证错误收敛为领域中文文案', async () => {
    queueResponses(
      jsonResponse(
        { detail: '用户名或密码错误', code: 106 },
        401
      )
    )
    const error = await request('GET', '/auth/me', undefined, {
      skipAuthRedirect: true,
    }).catch((e: unknown) => e)
    const apiError = error as ApiError
    expect(apiError.code).toBe(ApiErrorCode.AUTH_CREDENTIALS_INVALID)
    expect(apiError.userMessage).toBe('登录失败：用户名或密码错误')
  })

  it('401 + skipAuthRedirect：抛错且不触发会话过期/不清理 token', async () => {
    authTokenStore.set('kept-token')
    const expiredListener = vi.fn()
    const off = onSessionExpired(expiredListener)
    const handler = vi.fn()
    setSessionExpiredHandler(handler)

    queueResponses(
      jsonResponse({ detail: '用户名或密码错误', code: 106 }, 401)
    )
    const error = await request('GET', '/auth/login', undefined, {
      skipAuthRedirect: true,
    }).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(expiredListener).not.toHaveBeenCalled()
    expect(handler).not.toHaveBeenCalled()
    expect(authTokenStore.get()).toBe('kept-token')
    off()
    setSessionExpiredHandler(null)
  })

  it('401 + refresh 成功：重试原请求并更新 token', async () => {
    authTokenStore.set('expired-token')
    queueResponses(
      jsonResponse({ detail: 'token 已过期' }, 401),
      jsonResponse({ access_token: 'fresh-token', token_type: 'Bearer' }),
      jsonResponse({ success: true, code: 0, data: { id: 9 } })
    )
    const data = await request<{ id: number }>('GET', '/tasks/9')
    expect(data).toEqual({ id: 9 })
    expect(authTokenStore.get()).toBe('fresh-token')
    expect(fetchMock).toHaveBeenCalledTimes(3)
    // 第三次（重试）携带新 token
    const retryInit = fetchMock.mock.calls[2][1] as RequestInit
    expect((retryInit.headers as Record<string, string>).Authorization).toBe(
      'Bearer fresh-token'
    )
  })

  it('401 + refresh 失败：触发会话过期（清 token + 通知 + 整页跳转）并抛错', async () => {
    authTokenStore.set('expired-token')
    const expiredListener = vi.fn()
    const off = onSessionExpired(expiredListener)
    const handler = vi.fn()
    setSessionExpiredHandler(handler)

    queueResponses(
      jsonResponse({ detail: 'token 已过期' }, 401),
      jsonResponse({ detail: '刷新失败' }, 401)
    )
    const error = await request('GET', '/tasks/9').catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(expiredListener).toHaveBeenCalledTimes(1)
    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler.mock.calls[0][0]).toBe('/login?redirect=%2F')
    expect(authTokenStore.get()).toBeNull()
    off()
    setSessionExpiredHandler(null)
  })

  it('401 + refresh 失败且未注册 handler：默认整页跳登录（P2-1 回归）', async () => {
    authTokenStore.set('expired-token')
    setSessionExpiredHandler(null)
    // jsdom 的 window.location.assign 不可 spy（Location 实例非扩展），
    // 整体重定义 window.location 为桩观察默认跳转
    const originalLocation = window.location
    const assignMock = vi.fn()
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        pathname: '/',
        search: '',
        origin: 'http://localhost:3000',
        assign: assignMock,
      },
    })

    try {
      queueResponses(
        jsonResponse({ detail: 'token 已过期' }, 401),
        jsonResponse({ detail: '刷新失败' }, 401)
      )
      const error = await request('GET', '/tasks/9').catch((e: unknown) => e)

      expect(error).toBeInstanceOf(ApiError)
      expect(authTokenStore.get()).toBeNull()
      expect(assignMock).toHaveBeenCalledTimes(1)
      expect(assignMock).toHaveBeenCalledWith('/login?redirect=%2F')
    } finally {
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: originalLocation,
      })
    }
  })

  it('网络失败 → ApiError 统一网络文案', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const error = await request('GET', '/tasks').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    const apiError = error as ApiError
    expect(apiError.httpStatus).toBeNull()
    expect(apiError.userMessage).toBe(NETWORK_FAILED_COPY)
  })
})

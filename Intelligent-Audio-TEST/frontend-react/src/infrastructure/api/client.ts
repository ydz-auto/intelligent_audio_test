/**
 * 统一 fetch 封装（infrastructure/api 层；接线基座 INT-605）。
 *
 * 替换原 throw 桩，实现四通道：
 * - baseURL：相对路径 /api/v1（api_gateway/app.py:140-169 全路由挂载前缀）；
 *   dev 走 dev server 代理 → http://localhost:5000（service_ports.py gateway=5000，
 *   旧 Vue .env.development VITE_API_TARGET 同款，rsbuild.config.ts proxy 已配）。
 * - JWT auth token：请求自动注入 Authorization: Bearer（token 存取
 *   infrastructure/storage/auth-token）；401 语义对照旧 Vue http/client.ts——
 *   skipAuthRedirect 特例（密码错误 401 不触发登出跳转循环）、refresh 流程、
 *   AUTH_CREDENTIALS_INVALID(106) 分流。
 * - 错误码映射：error_response { success, code, message, detail, errors } 归一为
 *   ApiError（code=领域错误码枚举、userMessage=中文文案），拒绝魔法数字/字符串。
 * - SSE：/api/v1/sse 订阅封装见 infrastructure/realtime/sse.ts（本层请求出口共用）。
 */
import { ApiError } from './api-error'
import { ApiErrorCode, HttpStatus } from '@/domain/models/api'
import { sanitizeAuthRedirect } from '@/domain/lib/auth-redirect'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

/** 网关统一挂载前缀（api_gateway/app.py 全路由 /api/v1/*；dev 经代理到 localhost:5000） */
export const API_BASE_URL = '/api/v1'

export interface ApiRequestOptions extends Omit<RequestInit, 'body'> {
  /** query 参数（任意方法生效；undefined/null 值剔除） */
  params?: Record<string, unknown>
  /** 跳过 401 自动登出/跳转（login/register/encryption-key 等公开端点） */
  skipAuthRedirect?: boolean
  /** 响应类型（默认 json） */
  responseType?: 'json' | 'blob' | 'arraybuffer' | 'text'
  /** 关闭统一信封解包（默认 { success, code, message, data } → data） */
  unwrapResponse?: boolean
  /** 表单编码（application/x-www-form-urlencoded；登录接口 Form(...) 契约） */
  formUrlEncoded?: boolean
  /** 内部标记：401 已 refresh 重试过一次 */
  _retried?: boolean
}

// ===== 会话过期（401 且 refresh 失效）=====

export type SessionExpiredHandler = (redirectTo: string) => void

let sessionExpiredHandler: SessionExpiredHandler | null = null
const sessionExpiredListeners = new Set<SessionExpiredHandler>()

/** 注册会话过期监听（auth-store 清空登录态用）；返回解绑函数 */
export function onSessionExpired(listener: SessionExpiredHandler): () => void {
  sessionExpiredListeners.add(listener)
  return () => {
    sessionExpiredListeners.delete(listener)
  }
}

/** 覆盖默认整页跳登录行为（测试注入 / 认证卡接路由跳转） */
export function setSessionExpiredHandler(
  handler: SessionExpiredHandler | null
): void {
  sessionExpiredHandler = handler
}

function sessionExpired(): void {
  authTokenStore.clear()
  const current = `${window.location.pathname}${window.location.search}`
  const redirectTo = `/login?redirect=${encodeURIComponent(current)}`
  for (const listener of sessionExpiredListeners) {
    try {
      listener(redirectTo)
    } catch {
      // 监听器失败不阻断其余处理
    }
  }
  if (sessionExpiredHandler) {
    sessionExpiredHandler(redirectTo)
    return
  }
  // 默认整页跳登录（对照旧 Vue http/client.ts 401 即清态+跳 #/login?redirect=）；
  // 仅在无 handler 注册时兜底，redirect 经 sanitizeAuthRedirect 校验防注入
  const safeRedirect = sanitizeAuthRedirect(redirectTo, window.location.origin)
  if (safeRedirect) {
    window.location.assign(safeRedirect)
  }
}

// ===== URL / 请求体 / 请求头 =====

function buildUrl(path: string, options: ApiRequestOptions): string {
  let url = `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
  if (options.params) {
    const query = new URLSearchParams(
      Object.entries(options.params)
        .filter(([, value]) => value !== undefined && value !== null)
        .map(([key, value]) => [key, String(value)])
    ).toString()
    if (query) {
      url += `${url.includes('?') ? '&' : '?'}${query}`
    }
  }
  return url
}

function buildHeaders(
  body: unknown,
  options: ApiRequestOptions
): Record<string, string> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const token = authTokenStore.get()
  if (token) headers.Authorization = `Bearer ${token}`
  const isForm = body instanceof FormData
  const isSearch = body instanceof URLSearchParams
  if (options.formUrlEncoded || isSearch) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
  } else if (body !== undefined && body !== null && !isForm) {
    headers['Content-Type'] = 'application/json'
  }
  if (options.headers) {
    Object.assign(headers, options.headers as Record<string, string>)
  }
  return headers
}

function serializeBody(
  body: unknown,
  options: ApiRequestOptions
): BodyInit | undefined {
  if (body === undefined || body === null) return undefined
  if (body instanceof FormData || body instanceof URLSearchParams) return body
  if (typeof body === 'string') return body
  if (options.formUrlEncoded) {
    return new URLSearchParams(body as Record<string, string>)
  }
  return JSON.stringify(body)
}

// ===== 响应处理 =====

/** 统一信封解包：{ success, code, message, data, detail } → data；无信封原样返回 */
function unwrapEnvelope(data: unknown): unknown {
  if (typeof data === 'object' && data !== null) {
    const record = data as Record<string, unknown>
    const hasEnvelope = record.success !== undefined || record.code !== undefined
    if (hasEnvelope) {
      const code = typeof record.code === 'number' ? record.code : undefined
      const success = record.success === true
      const isOk =
        code === ApiErrorCode.SUCCESS ||
        code === HttpStatus.OK ||
        code === HttpStatus.CREATED ||
        success
      if (!isOk) {
        throw new ApiError({
          code,
          httpStatus: null,
          message: typeof record.message === 'string' ? record.message : '',
          detail: record.detail,
          errors: record.errors,
        })
      }
      return record.data ?? null
    }
  }
  return data
}

async function readBody(response: Response, options: ApiRequestOptions): Promise<unknown> {
  if (options.responseType === 'blob') return response.blob()
  if (options.responseType === 'arraybuffer') return response.arrayBuffer()
  if (options.responseType === 'text') return response.text()
  try {
    return await response.json()
  } catch {
    const text = await response.text()
    if (text.trim().startsWith('<')) {
      throw new ApiError({
        httpStatus: response.status,
        message: `服务器返回了 HTML（${response.status}）`,
      })
    }
    throw new ApiError({
      httpStatus: response.status,
      message: `服务器返回无效 JSON（${response.status}）`,
    })
  }
}

async function buildApiError(response: Response): Promise<ApiError> {
  let payload: {
    message?: unknown
    detail?: unknown
    code?: unknown
    errors?: unknown
  } = {}
  try {
    const text = await response.text()
    if (text) payload = JSON.parse(text) as typeof payload
  } catch {
    // 非 JSON 错误体，走 HTTP 状态码兜底文案
  }
  return new ApiError({
    code: payload.code,
    httpStatus: response.status,
    message: typeof payload.message === 'string' ? payload.message : '',
    detail: payload.detail,
    errors: payload.errors,
  })
}

/** 401 刷新流程：POST /auth/refresh 换新 token，成功落 storage 返回 true */
async function tryRefreshToken(): Promise<boolean> {
  const token = authTokenStore.get()
  if (!token) return false
  try {
    const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
    })
    if (!response.ok) return false
    const json = await response.json()
    const payload = unwrapEnvelope(json)
    const next =
      typeof payload === 'object' && payload !== null
        ? ((payload as Record<string, unknown>).access_token as string | undefined)
        : undefined
    if (typeof next !== 'string' || !next) return false
    authTokenStore.set(next)
    return true
  } catch {
    return false
  }
}

// ===== 核心请求 =====

export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options: ApiRequestOptions = {}
): Promise<T> {
  const url = buildUrl(path, options)
  const headers = buildHeaders(body, options)

  let response: Response
  try {
    response = await fetch(url, {
      method,
      headers,
      body: serializeBody(body, options),
      signal: options.signal,
      credentials: options.credentials,
    })
  } catch (err) {
    // fetch 网络层失败（DNS/TCP/代理不可达）→ 统一网络文案（isNetworkError 标记）
    throw new ApiError({
      httpStatus: null,
      message: '',
      detail: err instanceof Error ? err.message : String(err),
      isNetworkError: true,
    })
  }

  if (!response.ok) {
    if (response.status === 401 && !options.skipAuthRedirect && !options._retried) {
      if (await tryRefreshToken()) {
        return request<T>(method, path, body, { ...options, _retried: true })
      }
      sessionExpired()
    }
    throw await buildApiError(response)
  }

  const data = await readBody(response, options)
  if (options.unwrapResponse === false) return data as T
  return unwrapEnvelope(data) as T
}

/** 便捷客户端（各域 api 模块统一出口） */
export const apiClient = {
  get: <T>(path: string, options?: ApiRequestOptions): Promise<T> =>
    request<T>('GET', path, undefined, options),
  post: <T>(path: string, body?: unknown, options?: ApiRequestOptions): Promise<T> =>
    request<T>('POST', path, body, options),
  put: <T>(path: string, body?: unknown, options?: ApiRequestOptions): Promise<T> =>
    request<T>('PUT', path, body, options),
  patch: <T>(path: string, body?: unknown, options?: ApiRequestOptions): Promise<T> =>
    request<T>('PATCH', path, body, options),
  delete: <T>(path: string, options?: ApiRequestOptions): Promise<T> =>
    request<T>('DELETE', path, undefined, options),
}

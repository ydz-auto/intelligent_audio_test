/**
 * authApi 真实接口单测（认证接线 INT-606）：
 * login 表单编码 + 密文字段 / register JSON + 密文字段（禁用时明文兜底）/
 * fetchEncryptionKey 缓存与 Disabled/Unavailable 语义 / listPublicOAuthProviders
 * 映射 / getOAuthAuthorizeUrl 契约。
 * 密码加密原语 mock（password-encryption），避免依赖真实 WebCrypto 与 RSA 密钥。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/infrastructure/api/api-error'
import {
  API_BASE_URL,
  setSessionExpiredHandler,
} from '@/infrastructure/api/client'
import {
  PasswordEncryptionDisabledError,
  PasswordEncryptionUnavailableError,
} from '@/infrastructure/api/password-encryption'
import {
  authApi,
  fetchEncryptionKey,
  resetEncryptionKeyCache,
} from '@/infrastructure/api/authApi'
import { authTokenStore } from '@/infrastructure/storage/auth-token'
import { ApiErrorCode } from '@/domain/models/api'

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

vi.mock('@/infrastructure/api/password-encryption', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/infrastructure/api/password-encryption')>()
  return {
    ...actual,
    encryptPassword: vi.fn(
      async (
        password: string,
        fetchKey: () => Promise<{ kid: string; publicKey: string }>
      ) => {
        const key = await fetchKey()
        return {
          passwordEncrypted: `enc:${password}`,
          encryptionKeyId: key.kid,
        }
      }
    ),
  }
})

import { encryptPassword } from '@/infrastructure/api/password-encryption'

const ENCRYPTION_KEY_PAYLOAD = {
  success: true,
  code: 0,
  data: {
    enabled: true,
    kid: 'kid-1',
    public_key: 'PUBLIC_KEY_PEM',
    fallback: { kid: 'kid-fb', public_key: 'FALLBACK_PEM' },
  },
}

describe('authApi 真实接口', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
    vi.mocked(encryptPassword).mockClear()
    authTokenStore.clear()
    setSessionExpiredHandler(null)
    resetEncryptionKeyCache()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    authTokenStore.clear()
    setSessionExpiredHandler(null)
  })

  describe('fetchEncryptionKey', () => {
    it('enabled=true 返回 kid + publicKey，并缓存降级公钥', async () => {
      queueResponses(jsonResponse(ENCRYPTION_KEY_PAYLOAD))
      const key = await fetchEncryptionKey()
      expect(key).toEqual({
        kid: 'kid-1',
        publicKey: 'PUBLIC_KEY_PEM',
        fallback: { kid: 'kid-fb', publicKey: 'FALLBACK_PEM' },
      })
      expect(fetchMock).toHaveBeenCalledTimes(1)
      // 5 分钟缓存：二次调用不再请求
      await fetchEncryptionKey()
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    it('enabled=false 抛 PasswordEncryptionDisabledError（走明文路径）', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, data: { enabled: false } })
      )
      await expect(fetchEncryptionKey()).rejects.toBeInstanceOf(
        PasswordEncryptionDisabledError
      )
    })

    it('缺 kid/public_key 抛 PasswordEncryptionUnavailableError（不回退明文）', async () => {
      queueResponses(
        jsonResponse({
          success: true,
          code: 0,
          data: { enabled: true, kid: '', public_key: '' },
        })
      )
      await expect(fetchEncryptionKey()).rejects.toBeInstanceOf(
        PasswordEncryptionUnavailableError
      )
    })
  })

  describe('login（表单编码 + 密文）', () => {
    it('加密启用：以 x-www-form-urlencoded 提交 password_encrypted + encryption_key_id', async () => {
      queueResponses(
        jsonResponse(ENCRYPTION_KEY_PAYLOAD),
        jsonResponse({
          access_token: 't1',
          token_type: 'Bearer',
          user: { id: 1, username: 'admin', role_id: 2, role_name: '管理员', permissions: ['*'] },
        })
      )
      const result = await authApi.login({
        username: 'admin',
        password: 'secret',
      })
      expect(result.accessToken).toBe('t1')
      expect(result.user.username).toBe('admin')

      const loginCall = fetchMock.mock.calls[1] as [string, RequestInit]
      expect(loginCall[0]).toBe(`${API_BASE_URL}/auth/login`)
      const headers = loginCall[1].headers as Record<string, string>
      expect(headers['Content-Type']).toBe('application/x-www-form-urlencoded')
      const params = loginCall[1].body as URLSearchParams
      expect(params.get('username')).toBe('admin')
      expect(params.get('password_encrypted')).toBe('enc:secret')
      expect(params.get('encryption_key_id')).toBe('kid-1')
      expect(params.get('password')).toBeNull()
    })

    it('加密禁用（enabled=false）：回退明文字段 password', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, data: { enabled: false } }),
        jsonResponse({
          access_token: 't2',
          token_type: 'Bearer',
          user: { id: 2, username: 'guest', role_id: null, role_name: '', permissions: [] },
        })
      )
      const result = await authApi.login({
        username: 'guest',
        password: 'plain',
      })
      expect(result.accessToken).toBe('t2')
      const loginCall = fetchMock.mock.calls[1] as [string, RequestInit]
      const params = loginCall[1].body as URLSearchParams
      expect(params.get('password')).toBe('plain')
      expect(params.get('password_encrypted')).toBeNull()
    })

    it('密码错误 401：抛 ApiError 且不清理 token（skipAuthRedirect 语义）', async () => {
      authTokenStore.set('kept')
      queueResponses(
        jsonResponse(ENCRYPTION_KEY_PAYLOAD),
        jsonResponse({ detail: '用户名或密码错误', code: 106 }, 401)
      )
      const error = await authApi
        .login({ username: 'admin', password: 'wrong' })
        .catch((e: unknown) => e)
      expect(error).toBeInstanceOf(ApiError)
      expect((error as ApiError).code).toBe(ApiErrorCode.AUTH_CREDENTIALS_INVALID)
      expect(authTokenStore.get()).toBe('kept')
    })
  })

  describe('register（JSON + 密文）', () => {
    it('加密启用：JSON body 提交 username/email/password_encrypted/encryption_key_id', async () => {
      queueResponses(
        jsonResponse(ENCRYPTION_KEY_PAYLOAD),
        jsonResponse({ success: true, code: 0, data: { user_id: 42 } })
      )
      const result = await authApi.register({
        username: 'new_user',
        email: 'new@example.com',
        password: 'secret1',
      })
      expect(result.userId).toBe(42)

      const registerCall = fetchMock.mock.calls[1] as [string, RequestInit]
      expect(registerCall[0]).toBe(`${API_BASE_URL}/auth/register`)
      const headers = registerCall[1].headers as Record<string, string>
      expect(headers['Content-Type']).toBe('application/json')
      const body = JSON.parse(String(registerCall[1].body)) as Record<string, string>
      expect(body).toEqual({
        username: 'new_user',
        email: 'new@example.com',
        password_encrypted: 'enc:secret1',
        encryption_key_id: 'kid-1',
      })
    })

    it('加密禁用：回退明文字段 password', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, data: { enabled: false } }),
        jsonResponse({ success: true, code: 0, data: { user_id: 7 } })
      )
      const result = await authApi.register({
        username: 'u',
        email: 'u@example.com',
        password: 'plain',
      })
      expect(result.userId).toBe(7)
      const registerCall = fetchMock.mock.calls[1] as [string, RequestInit]
      const body = JSON.parse(String(registerCall[1].body)) as Record<string, string>
      expect(body.password).toBe('plain')
      expect(body.password_encrypted).toBeUndefined()
    })

    it('注册开关关闭（403）：抛 ApiError httpStatus=403（表单层切引导态）', async () => {
      queueResponses(
        jsonResponse(ENCRYPTION_KEY_PAYLOAD),
        jsonResponse(
          { success: false, code: 203, message: '注册未开放', detail: '注册未开放' },
          403
        )
      )
      const error = await authApi
        .register({ username: 'u', email: 'u@example.com', password: 'p1' })
        .catch((e: unknown) => e)
      expect(error).toBeInstanceOf(ApiError)
      const apiError = error as ApiError
      expect(apiError.httpStatus).toBe(403)
      expect(apiError.userMessage).toBe('注册未开放')
    })
  })

  describe('listPublicOAuthProviders', () => {
    it('映射返回 OAuthProvider[]（id 数值转字符串，icon 透传）', async () => {
      queueResponses(
        jsonResponse({
          success: true,
          code: 0,
          data: {
            providers: [
              { id: 1, name: 'GitHub', slug: 'github', icon: 'github' },
              { id: 2, name: '企业统一认证', slug: 'oidc', icon: 'oidc' },
            ],
          },
        })
      )
      const providers = await authApi.listPublicOAuthProviders()
      expect(providers).toEqual([
        { id: '1', name: 'GitHub', slug: 'github', icon: 'github' },
        { id: '2', name: '企业统一认证', slug: 'oidc', icon: 'oidc' },
      ])
    })

    it('空 providers：返回空数组', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, data: { providers: [] } })
      )
      expect(await authApi.listPublicOAuthProviders()).toEqual([])
    })
  })

  describe('getOAuthAuthorizeUrl', () => {
    it('默认 intent=login：/api/v1/auth/oauth/{slug}/authorize', () => {
      expect(authApi.getOAuthAuthorizeUrl('github')).toBe(
        `${API_BASE_URL}/auth/oauth/github/authorize`
      )
    })

    it('intent=bind：追加 ?intent=bind', () => {
      expect(authApi.getOAuthAuthorizeUrl('github', 'bind')).toBe(
        `${API_BASE_URL}/auth/oauth/github/authorize?intent=bind`
      )
    })

    it('slug 编码防注入', () => {
      expect(authApi.getOAuthAuthorizeUrl('a/b?c=1')).toBe(
        `${API_BASE_URL}/auth/oauth/a%2Fb%3Fc%3D1/authorize`
      )
    })
  })
})

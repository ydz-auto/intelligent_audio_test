/**
 * auth-store 真实登录态单测（接线基座 INT-605）。
 * mock 依赖 infrastructure/api/authApi（登录/登出/会话恢复接口出口），
 * 断言 store 对 token（storage）与 user 状态的管理及会话过期联动。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/infrastructure/api/api-error'
import { request, setSessionExpiredHandler } from '@/infrastructure/api/client'
import { authTokenStore } from '@/infrastructure/storage/auth-token'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

vi.mock('@/infrastructure/api/authApi', () => ({
  authApi: {
    login: vi.fn(),
    getMe: vi.fn(),
    logout: vi.fn(),
    getAuthMode: vi.fn(),
  },
}))

import { authApi } from '@/infrastructure/api/authApi'

const demoUser = {
  id: '1',
  username: 'admin',
  displayName: '管理员',
  roleName: '超级管理员',
  permissions: ['*'],
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('auth-store 真实登录态', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null })
    authTokenStore.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    authTokenStore.clear()
    setSessionExpiredHandler(null)
  })

  it('login：真实接口回包落 token（storage）与 user', async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      accessToken: 'access-1',
      user: demoUser,
    })
    await useAuthStore.getState().login({ username: 'admin', password: 'pw' })
    expect(authTokenStore.get()).toBe('access-1')
    expect(useAuthStore.getState().user?.username).toBe('admin')
  })

  it('hydrateSession：有 token 时 GET /auth/me 回填 user', async () => {
    authTokenStore.set('t1')
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: '2',
      username: 'tester',
      displayName: 'tester',
      roleName: '',
      permissions: ['task:read'],
    })
    await useAuthStore.getState().hydrateSession()
    expect(authApi.getMe).toHaveBeenCalledTimes(1)
    expect(useAuthStore.getState().user?.username).toBe('tester')
  })

  it('hydrateSession：无 token 不发请求', async () => {
    await useAuthStore.getState().hydrateSession()
    expect(authApi.getMe).not.toHaveBeenCalled()
    expect(useAuthStore.getState().user).toBeNull()
  })

  it('loginWithToken：OAuth 回调 token 落 storage + GET /auth/me 回填 user', async () => {
    authTokenStore.set('oauth-prefill')
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: '3',
      username: 'oauth_user',
      displayName: 'oauth_user',
      roleName: '',
      permissions: ['home:read'],
    })
    await useAuthStore.getState().loginWithToken('oauth-token-1')
    expect(authTokenStore.get()).toBe('oauth-token-1')
    expect(useAuthStore.getState().user?.username).toBe('oauth_user')
  })

  it('logout：清 token 与 user（登出接口旁路）', async () => {
    authTokenStore.set('t1')
    useAuthStore.setState({ user: demoUser })
    vi.mocked(authApi.logout).mockResolvedValue(undefined)

    await useAuthStore.getState().logout()

    expect(authApi.logout).toHaveBeenCalledTimes(1)
    expect(authTokenStore.get()).toBeNull()
    expect(useAuthStore.getState().user).toBeNull()
  })

  it('会话过期：client 401+refresh 失败 → 联动清空 user 登录态', async () => {
    useAuthStore.setState({ user: demoUser })
    authTokenStore.set('expired')
    setSessionExpiredHandler(vi.fn()) // 屏蔽默认整页跳转

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: 'token 已过期' }, 401))
      .mockResolvedValueOnce(jsonResponse({ detail: '刷新失败' }, 401))
    vi.stubGlobal('fetch', fetchMock)

    await expect(request('GET', '/tasks')).rejects.toBeInstanceOf(ApiError)

    expect(authTokenStore.get()).toBeNull()
    expect(useAuthStore.getState().user).toBeNull()
  })
})

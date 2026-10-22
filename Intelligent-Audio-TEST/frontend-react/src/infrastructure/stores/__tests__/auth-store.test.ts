/**
 * auth-store 真实登录态单测（接线基座 INT-605）。
 * mock 依赖 infrastructure/api/authApi（登录/登出/会话恢复接口出口），
 * 断言 store 对 token（storage）与 user 状态的管理及会话过期联动。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/infrastructure/api/api-error'
import { request, setSessionExpiredHandler } from '@/infrastructure/api/client'
import { authTokenStore } from '@/infrastructure/storage/auth-token'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import {
  resetAuthSessionBootstrap,
  useAuthStore,
  ensureAuthSession,
} from '@/infrastructure/stores/auth-store'

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
    resetAuthSessionBootstrap()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    authTokenStore.clear()
    resetAuthSessionBootstrap()
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

  it('hydrateSession：/auth/me 契约缺 role_name → 保留登录时缓存的 roleName（INT-1226）', async () => {
    authTokenStore.set('t1')
    // 登录完成后 persist 缓存了角色名（来自 POST /auth/login user.role_name）
    useAuthStore.setState({
      user: {
        id: '369',
        username: '接线测试_admin',
        displayName: '接线测试_admin',
        roleName: '超级管理员',
        permissions: ['*'],
      },
    })
    // mock 模拟真实 getMe：fallback 透传（DTO 层 ROLE_META 映射由 authApi 单测覆盖）
    vi.mocked(authApi.getMe).mockImplementation(
      async (_options?: object, fallbackRoleName = '') => ({
        id: '369',
        username: '接线测试_admin',
        displayName: '接线测试_admin',
        roleName: fallbackRoleName,
        permissions: ['*'],
      })
    )
    await useAuthStore.getState().hydrateSession()
    expect(authApi.getMe).toHaveBeenCalledWith({}, '超级管理员')
    expect(useAuthStore.getState().user?.roleName).toBe('超级管理员')
  })

  it('hydrateSession：缓存 roleName 为角色码 → 透传给 getMe 映射中文名', async () => {
    authTokenStore.set('t1')
    // 历史 persist 数据可能存的是角色码（如 admin），恢复时由 getMe/DTO 映射为中文名
    useAuthStore.setState({
      user: {
        id: '369',
        username: '接线测试_admin',
        displayName: '接线测试_admin',
        roleName: 'admin',
        permissions: ['*'],
      },
    })
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: '369',
      username: '接线测试_admin',
      displayName: '接线测试_admin',
      roleName: '超级管理员',
      permissions: ['*'],
    })
    await useAuthStore.getState().hydrateSession()
    expect(authApi.getMe).toHaveBeenCalledWith({}, 'admin')
    expect(useAuthStore.getState().user?.roleName).toBe('超级管理员')
  })

  it('hydrateSession：无 token 且 AUTH_MODE=off → GET /auth/me 回填 dev_user（§3.1 开放模式放行）', async () => {
    vi.mocked(authApi.getAuthMode).mockResolvedValue('off')
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: '0',
      username: 'dev_user',
      displayName: 'dev_user',
      roleName: '',
      permissions: ['*'],
    })
    await useAuthStore.getState().hydrateSession()
    expect(authApi.getAuthMode).toHaveBeenCalledTimes(1)
    expect(authApi.getMe).toHaveBeenCalledWith({ skipAuthRedirect: true })
    expect(useAuthStore.getState().user?.username).toBe('dev_user')
    expect(useAuthStore.getState().user?.permissions).toEqual(['*'])
  })

  it('hydrateSession：无 token 且非 off 模式 → 不发 /auth/me，保持未登录态', async () => {
    vi.mocked(authApi.getAuthMode).mockResolvedValue('prod')
    await useAuthStore.getState().hydrateSession()
    expect(authApi.getAuthMode).toHaveBeenCalledTimes(1)
    expect(authApi.getMe).not.toHaveBeenCalled()
    expect(useAuthStore.getState().user).toBeNull()
  })

  it('ensureAuthSession：无 token 且 AUTH_MODE=off → dev_user 放行（守卫/挂载共用引导）', async () => {
    vi.mocked(authApi.getAuthMode).mockResolvedValue('off')
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: '0',
      username: 'dev_user',
      displayName: 'dev_user',
      roleName: '',
      permissions: ['*'],
    })
    await ensureAuthSession()
    expect(useAuthStore.getState().user?.username).toBe('dev_user')
    expect(authApi.getMe).toHaveBeenCalledTimes(1)
  })

  it('ensureAuthSession：并发调用共享同一次引导，不重复请求', async () => {
    vi.mocked(authApi.getAuthMode).mockResolvedValue('off')
    vi.mocked(authApi.getMe).mockImplementation(async () => {
      await new Promise((r) => setTimeout(r, 5))
      return {
        id: '0',
        username: 'dev_user',
        displayName: 'dev_user',
        roleName: '',
        permissions: ['*'],
      }
    })
    await Promise.all([ensureAuthSession(), ensureAuthSession(), ensureAuthSession()])
    expect(authApi.getAuthMode).toHaveBeenCalledTimes(1)
    expect(authApi.getMe).toHaveBeenCalledTimes(1)
    expect(useAuthStore.getState().user?.username).toBe('dev_user')
  })

  it('ensureAuthSession：登出后复位，允许重新引导（off 模式再放行）', async () => {
    vi.mocked(authApi.getAuthMode).mockResolvedValue('off')
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: '0',
      username: 'dev_user',
      displayName: 'dev_user',
      roleName: '',
      permissions: ['*'],
    })
    vi.mocked(authApi.logout).mockResolvedValue(undefined)

    // 首次引导 → dev_user 放行
    await ensureAuthSession()
    expect(useAuthStore.getState().user?.username).toBe('dev_user')

    // 登出清态并复位引导
    await useAuthStore.getState().logout()
    expect(useAuthStore.getState().user).toBeNull()

    // 登出后再次引导 → 重新判 off 模式并放行
    await ensureAuthSession()
    expect(useAuthStore.getState().user?.username).toBe('dev_user')
    expect(authApi.getAuthMode).toHaveBeenCalledTimes(2)
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

  it('logout：全局算法过滤随登出清空（多账号切换不串值，02_导航栏 §3.4 契约 6）', async () => {
    useAuthStore.setState({ user: demoUser })
    authTokenStore.set('t1')
    useAlgorithmStore.setState({ algorithmId: 'asr-v3' })
    vi.mocked(authApi.logout).mockResolvedValue(undefined)

    await useAuthStore.getState().logout()

    expect(useAlgorithmStore.getState().algorithmId).toBe('')
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

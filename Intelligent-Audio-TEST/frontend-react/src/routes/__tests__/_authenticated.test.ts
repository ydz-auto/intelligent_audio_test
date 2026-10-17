/**
 * _authenticated 认证守卫测试（INT-606 打回修复回归，12_登录与错误页.md §3.1）：
 * AUTH_MODE=off 开放模式无 token 时以 dev_user 放行（Vue AuthMode.OFF 口径），
 * 非 off 模式无登录态跳 /login。守卫 beforeLoad 直接调用（不挂 RouterProvider）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { authTokenStore } from '@/infrastructure/storage/auth-token'
import {
  resetAuthSessionBootstrap,
  useAuthStore,
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
import { Route as AuthenticatedRoute } from '@/routes/_authenticated'

const devUser = {
  id: '0',
  username: 'dev_user',
  displayName: 'dev_user',
  roleName: '',
  permissions: ['*'],
}

type BeforeLoadCtx = {
  location: { href: string }
}

/** 守卫抛出的 redirect 为 Response(307)，目标落在 options.to */
function redirectTarget(err: unknown): unknown {
  const options = (err as { options?: { to?: string } }).options
  return options?.to
}

function runGuard() {
  return AuthenticatedRoute.options.beforeLoad?.({
    location: { href: '/dashboard' },
  } as BeforeLoadCtx) as Promise<unknown>
}

describe('_authenticated 守卫 AUTH_MODE=off 放行', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null })
    authTokenStore.clear()
    resetAuthSessionBootstrap()
    vi.clearAllMocks()
  })

  it('AUTH_MODE=off 无 token：引导回填 dev_user 后放行（进入工作台可直达）', async () => {
    vi.mocked(authApi.getAuthMode).mockResolvedValue('off')
    vi.mocked(authApi.getMe).mockResolvedValue(devUser)

    await expect(runGuard()).resolves.toBeUndefined()
    expect(useAuthStore.getState().user?.username).toBe('dev_user')
  })

  it('已登录（token 会话）：引导刷新后放行', async () => {
    useAuthStore.setState({ user: devUser })
    authTokenStore.set('t1')
    vi.mocked(authApi.getMe).mockResolvedValue(devUser)

    await expect(runGuard()).resolves.toBeUndefined()
    expect(useAuthStore.getState().user?.username).toBe('dev_user')
  })

  it('非 off 模式无 token：跳回登录页', async () => {
    vi.mocked(authApi.getAuthMode).mockResolvedValue('prod')

    const redirect = await runGuard().catch((err) => err)
    expect(redirectTarget(redirect)).toBe('/login')
    expect(useAuthStore.getState().user).toBeNull()
  })
})

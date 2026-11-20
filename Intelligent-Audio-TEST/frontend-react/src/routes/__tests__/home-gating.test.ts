/**
 * 首页可见性守卫测试：注册后可见（含邀请码注册强制开启）时，未登录访问 /
 * 跳转登录页并携带回跳地址；已登录或策略关闭时正常放行。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { authApi } from '@/infrastructure/api/authApi'
import { Route as HomeRoute } from '@/routes/index'

const authState = vi.hoisted(() => ({
  user: null as { username: string } | null,
}))

vi.mock('@/features/home', () => ({ default: () => null }))

vi.mock('@/infrastructure/stores/auth-store', () => ({
  ensureAuthSession: vi.fn(async () => undefined),
  useAuthStore: { getState: () => authState },
}))

vi.mock('@/infrastructure/api/authApi', () => ({
  authApi: { getRegistrationPolicy: vi.fn() },
}))

/** 守卫抛出的 redirect 为 Response(307)，目标落在 options.to */
function redirectTarget(err: unknown): unknown {
  return (err as { options?: { to?: string } }).options?.to
}

function redirectSearch(err: unknown): unknown {
  return (err as { options?: { search?: unknown } }).options?.search
}

function runGuard() {
  const beforeLoad = HomeRoute.options.beforeLoad as () => Promise<unknown>
  return beforeLoad()
}

describe('首页可见性守卫', () => {
  beforeEach(() => {
    authState.user = null
    vi.clearAllMocks()
  })

  it('未登录且策略为注册后可见：跳登录页并携带回跳首页', async () => {
    vi.mocked(authApi.getRegistrationPolicy).mockResolvedValue({
      inviteCodeRequired: true,
      homeRequireRegistration: true,
    })

    const redirect = await runGuard().catch((err) => err)
    expect(redirectTarget(redirect)).toBe('/login')
    expect(redirectSearch(redirect)).toEqual({ redirect: '/' })
  })

  it('未登录且策略关闭：正常放行首页', async () => {
    vi.mocked(authApi.getRegistrationPolicy).mockResolvedValue({
      inviteCodeRequired: false,
      homeRequireRegistration: false,
    })

    await expect(runGuard()).resolves.toBeUndefined()
    expect(authApi.getRegistrationPolicy).toHaveBeenCalledTimes(1)
  })

  it('策略接口失败：按公开首页降级放行', async () => {
    vi.mocked(authApi.getRegistrationPolicy).mockRejectedValue(
      new Error('network')
    )

    await expect(runGuard()).resolves.toBeUndefined()
  })

  it('已登录：不查策略直接放行', async () => {
    authState.user = { username: 'tester' }

    await expect(runGuard()).resolves.toBeUndefined()
    expect(authApi.getRegistrationPolicy).not.toHaveBeenCalled()
  })
})

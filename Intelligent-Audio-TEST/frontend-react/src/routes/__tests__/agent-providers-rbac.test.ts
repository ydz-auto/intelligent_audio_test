/**
 * /agent-providers 路由权限守卫单测（INT-2493 §11 / 卡面验收 10）：
 * 无 agent:provider:manage → /403?from=/agent-providers；持码放行。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { Route as AgentProvidersRoute } from '@/routes/_authenticated/agent-providers'

vi.mock('@/infrastructure/api/authApi', () => ({
  authApi: {
    login: vi.fn(),
    getMe: vi.fn(),
    logout: vi.fn(),
    getAuthMode: vi.fn(),
  },
}))

const guest = {
  id: '3',
  username: 'guest',
  displayName: 'guest',
  roleName: '游客',
  permissions: ['report:read'],
}

function redirectOptions(err: unknown): { to?: string; search?: { from?: string } } {
  return (err as { options?: { to?: string; search?: { from?: string } } }).options ?? {}
}

function runGuard(): Promise<unknown> {
  const beforeLoad = AgentProvidersRoute.options.beforeLoad
  if (!beforeLoad) return Promise.resolve(undefined)
  return Promise.resolve().then(() =>
    beforeLoad({
      location: { pathname: '/agent-providers', href: '/agent-providers' },
    } as Parameters<typeof beforeLoad>[0])
  )
}

describe('/agent-providers 路由权限守卫', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null })
    vi.clearAllMocks()
  })

  it('无 agent:provider:manage：抛 /403 并携带 from', async () => {
    useAuthStore.setState({ user: guest })
    const err = await runGuard().catch((e) => e)
    expect(redirectOptions(err).to).toBe('/403')
    expect(redirectOptions(err).search?.from).toBe('/agent-providers')
  })

  it('持 agent:provider:manage：放行不抛', async () => {
    useAuthStore.setState({
      user: { ...guest, permissions: ['agent:provider:manage'] },
    })
    await expect(runGuard()).resolves.toBeUndefined()
  })

  it('admin 通配 *：放行不抛', async () => {
    useAuthStore.setState({ user: { ...guest, permissions: ['*'] } })
    await expect(runGuard()).resolves.toBeUndefined()
  })
})

/**
 * /agent-skills 路由权限守卫单测（INT-2550 卡面验收 12）：
 * 无 agent:skill:manage → /403?from=/agent-skills；持码 / 通配放行。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { Route as AgentSkillsRoute } from '@/routes/_authenticated/agent-skills'

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
  const beforeLoad = AgentSkillsRoute.options.beforeLoad
  if (!beforeLoad) return Promise.resolve(undefined)
  return Promise.resolve().then(() =>
    beforeLoad({
      location: { pathname: '/agent-skills', href: '/agent-skills' },
      params: {},
      search: {},
      context: {},
      cause: 'enter',
      abortController: new AbortController(),
      preload: false,
      matches: [],
    } as unknown as Parameters<typeof beforeLoad>[0])
  )
}

describe('/agent-skills 路由权限守卫', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null })
    vi.clearAllMocks()
  })

  it('无 agent:skill:manage：抛 /403 并携带 from', async () => {
    useAuthStore.setState({ user: guest })
    const err = await runGuard().catch((e) => e)
    expect(redirectOptions(err).to).toBe('/403')
    expect(redirectOptions(err).search?.from).toBe('/agent-skills')
  })

  it('持 agent:skill:manage：放行不抛', async () => {
    useAuthStore.setState({
      user: { ...guest, permissions: ['agent:skill:manage'] },
    })
    await expect(runGuard()).resolves.toBeUndefined()
  })

  it('admin 通配 *：放行不抛', async () => {
    useAuthStore.setState({ user: { ...guest, permissions: ['*'] } })
    await expect(runGuard()).resolves.toBeUndefined()
  })
})

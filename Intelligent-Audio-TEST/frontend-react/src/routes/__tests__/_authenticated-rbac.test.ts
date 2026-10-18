/**
 * 路由级 RBAC 守卫测试（接线·壳 INT-607，12_登录与错误页.md §4.3 + 00 总表 §4.3）：
 * _authenticated 组内页面 beforeLoad 无权限 → /403?from={来源路径}（403 页回显），
 * 替换现 Vue「无权限跳首页」静默行为。代表路由取 /logs（log:read，轻依赖路由）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { Route as LogsRoute } from '@/routes/_authenticated/logs'

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

function runLogsGuard(): Promise<unknown> {
  const beforeLoad = LogsRoute.options.beforeLoad
  if (!beforeLoad) return Promise.resolve(undefined)
  // beforeLoad 为同步守卫（requirePermission 同步抛 redirect）——经 Promise 链把同步抛转 rejection
  return Promise.resolve().then(() =>
    beforeLoad({
      location: { pathname: '/logs', href: '/logs' },
    } as Parameters<typeof beforeLoad>[0])
  )
}

describe('/logs 路由权限守卫', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null })
    vi.clearAllMocks()
  })

  it('无 log:read（guest）：抛 /403 并携带 from=/logs', async () => {
    useAuthStore.setState({ user: guest })
    const err = await runLogsGuard().catch((e) => e)
    expect(redirectOptions(err).to).toBe('/403')
    expect(redirectOptions(err).search?.from).toBe('/logs')
  })

  it('持 log:read：放行不抛', async () => {
    useAuthStore.setState({
      user: { ...guest, permissions: ['log:read'] },
    })
    await expect(runLogsGuard()).resolves.toBeUndefined()
  })

  it('超级通配 *：放行不抛', async () => {
    useAuthStore.setState({
      user: { ...guest, permissions: ['*'] },
    })
    await expect(runLogsGuard()).resolves.toBeUndefined()
  })
})

/**
 * 路由守卫单测（接线壳 INT-607，12_登录与错误页.md §4.3/§9）：
 * requirePermission / requireAnyPermission 校验真实会话权限，失败抛 redirect
 * 至 /403 且 search.from 携带目标路径 pathname（替换旧 Vue「无权限跳首页」）。
 */
import { beforeEach, describe, expect, it } from 'vitest'

import { useAuthStore } from '@/infrastructure/stores/auth-store'
import {
  requireAnyPermission,
  requirePermission,
} from '@/application/auth/route-guards'

const location = { pathname: '/tasks' } as const

/** redirect 对象的 search 载荷（TanStack Redirect options） */
function redirectPayload(err: unknown): {
  to?: unknown
  search?: Record<string, unknown>
} {
  const options = (err as { options?: { to?: unknown; search?: unknown } }).options
  return {
    to: options?.to,
    search: (options?.search ?? {}) as Record<string, unknown>,
  }
}

describe('requirePermission', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null })
  })

  it('持有权限码放行（不抛错）', () => {
    useAuthStore.setState({
      user: {
        id: '1',
        username: 'tester',
        displayName: 'tester',
        roleName: '测试工程师',
        permissions: ['task:read'],
      },
    })
    expect(() => requirePermission('task:read', location)).not.toThrow()
  })

  it("admin '*' 通配放行任意权限码", () => {
    useAuthStore.setState({
      user: {
        id: '1',
        username: 'admin',
        displayName: 'admin',
        roleName: '超级管理员',
        permissions: ['*'],
      },
    })
    expect(() => requirePermission('task:read', location)).not.toThrow()
  })

  it('未登录（无 user）→ /403?from=pathname', () => {
    let thrown: unknown
    try {
      requirePermission('task:read', location)
    } catch (err) {
      thrown = err
    }
    const payload = redirectPayload(thrown)
    expect(payload.to).toBe('/403')
    expect(payload.search?.from).toBe('/tasks')
  })

  it('无权限码 → /403?from=pathname（guest 直达业务页兜底）', () => {
    useAuthStore.setState({
      user: {
        id: '2',
        username: 'guest',
        displayName: 'guest',
        roleName: '游客',
        permissions: ['report:read'],
      },
    })
    let thrown: unknown
    try {
      requirePermission('task:read', location)
    } catch (err) {
      thrown = err
    }
    const payload = redirectPayload(thrown)
    expect(payload.to).toBe('/403')
    expect(payload.search?.from).toBe('/tasks')
  })
})

describe('requireAnyPermission', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null })
  })

  it('任一权限码命中即放行（SPL 双口径 spl:read/digital_spl:read）', () => {
    useAuthStore.setState({
      user: {
        id: '3',
        username: 'device_admin',
        displayName: 'device_admin',
        roleName: '设备管理员',
        permissions: ['spl:read'],
      },
    })
    expect(() =>
      requireAnyPermission(['spl:read', 'digital_spl:read'], location)
    ).not.toThrow()
  })

  it('集合无一命中 → /403?from（系统设置工作区四码集合对 algo_engineer 收窄后）', () => {
    useAuthStore.setState({
      user: {
        id: '4',
        username: 'algo',
        displayName: 'algo',
        roleName: '算法工程师',
        permissions: ['algorithm:read', 'report:read'],
      },
    })
    let thrown: unknown
    try {
      requireAnyPermission(
        ['user:read', 'role:read', 'auth:manage_provider', 'log:manage'],
        location
      )
    } catch (err) {
      thrown = err
    }
    const payload = redirectPayload(thrown)
    expect(payload.to).toBe('/403')
    expect(payload.search?.from).toBe('/tasks')
  })
})

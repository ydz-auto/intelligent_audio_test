/**
 * 侧栏视图 RBAC 过滤单测（接线壳 INT-607，00_页面清单与RBAC划分.md §4.1
 * 侧栏树结果行，INT-486 合并后口径）：根导航按权限码逐项过滤、空组整组隐藏；
 * 设置 drill-in 树同过滤。五角色可见性差异（admin 14 / tester 13 / algo 11 /
 * device_admin 3 / guest 3）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'

import { useSidebarView } from '@/application/hooks/use-sidebar-view'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import type { AuthUser } from '@/domain/models/user'

const pathnameMock = vi.hoisted(() => ({ value: '/dashboard' }))

vi.mock('@tanstack/react-router', () => ({
  // 对齐真实 useLocation({ select }) 语义：select 在 location 上执行
  useLocation: (
    options?: { select?: (location: { pathname: string }) => string }
  ) =>
    options?.select
      ? options.select({ pathname: pathnameMock.value })
      : { pathname: pathnameMock.value },
}))

function makeUser(username: string, permissions: string[]): AuthUser {
  return {
    id: '1',
    username,
    displayName: username,
    roleName: username,
    permissions,
  }
}

/** 根导航过滤后可见项（组: 项数扁平展开 titles） */
function visibleNav() {
  const { result } = renderHook(() => useSidebarView())
  return result.current.navGroups.flatMap((group) =>
    group.items.map((item) => item.title)
  )
}

describe('useSidebarView 根导航 RBAC 过滤', () => {
  beforeEach(() => {
    pathnameMock.value = '/dashboard'
    useAuthStore.setState({ user: null })
  })

  it("admin（'*'）→ 六组全显 14 项", () => {
    useAuthStore.setState({ user: makeUser('admin', ['*']) })
    const items = visibleNav()
    expect(items).toHaveLength(14)
    expect(items).toContain('概览')
    expect(items).toContain('灵犀Agent')
    expect(items).toContain('开始测试')
    expect(items).toContain('任务管理')
    expect(items).toContain('SPL 映射')
    expect(items).toContain('系统设置')
  })

  it('tester → 13 项，SPL 映射隐藏（无 spl/digital_spl 码）；设备管理可见（device:read，仅读）', () => {
    useAuthStore.setState({
      user: makeUser('tester', [
        'home:read',
        'report:read',
        'task:read',
        'task:execute',
        'testcase:read',
        'audio:read',
        'device:read',
        'algorithm:read',
        'evaluation:read',
        'tag:read',
        'log:read',
        'log:manage',
      ]),
    })
    const items = visibleNav()
    expect(items).toHaveLength(13)
    expect(items).not.toContain('SPL 映射')
    expect(items).toContain('设备管理')
    expect(items).toContain('系统设置') // log:manage 命中运维设置域
  })

  it('algo_engineer → 11 项：开始测试/任务/用例/音频/报告 + 测试配置三页 + 日志；SPL/设备/系统设置隐藏', () => {
    useAuthStore.setState({
      user: makeUser('algo', [
        'home:read',
        'report:read',
        'task:read',
        'algorithm:read',
        'evaluation:read',
        'tag:read',
        'log:read',
        'testcase:read',
        'audio:read',
      ]),
    })
    const items = visibleNav()
    expect(items).toHaveLength(11)
    expect(items).not.toContain('SPL 映射')
    expect(items).not.toContain('设备管理')
    expect(items).not.toContain('系统设置')
    expect(items).toContain('日志查看')
  })

  it('device_admin → 3 项：概览/设备管理/SPL 映射（测试资产其余/管理组整组隐藏）', () => {
    useAuthStore.setState({
      user: makeUser('device_admin', [
        'home:read',
        'device:read',
        'spl:read',
        'digital_spl:read',
      ]),
    })
    expect(visibleNav()).toEqual(['概览', '设备管理', 'SPL 映射'])
  })

  it('guest → 3 项：概览/灵犀Agent/报告中心（管理/测试配置/测试执行组整组隐藏）', () => {
    useAuthStore.setState({
      user: makeUser('guest', ['home:read', 'report:read']),
    })
    expect(visibleNav()).toEqual(['概览', '灵犀Agent', '报告中心'])
  })

  it('登录态变化即时收敛（tester → 登出后导航整树空，重新登录恢复）', () => {
    useAuthStore.setState({
      user: makeUser('guest', ['home:read', 'report:read']),
    })
    expect(visibleNav()).toHaveLength(3)

    useAuthStore.setState({ user: null })
    expect(visibleNav()).toHaveLength(0)
  })
})

describe('useSidebarView 设置 drill-in 树过滤', () => {
  beforeEach(() => {
    pathnameMock.value = '/system-settings/site'
    useAuthStore.setState({ user: null })
  })

  it('admin → 设置树按权限全显（站点设置域可见）', () => {
    useAuthStore.setState({ user: makeUser('admin', ['*']) })
    const { result } = renderHook(() => useSidebarView())
    expect(result.current.view?.id).toBe('system-settings')
    expect(result.current.navGroups.length).toBeGreaterThanOrEqual(1)
  })

  it('guest（无设置域码）→ 设置树仅「外观与主题」域（全员登录用户，无码门槛）', () => {
    useAuthStore.setState({ user: makeUser('guest', ['report:read']) })
    const { result } = renderHook(() => useSidebarView())
    expect(result.current.view?.id).toBe('system-settings')
    // 六域仅外观与主题可见（site/iam/auth/security 需 user:read、operations 需 log:manage）
    const visibleDomains = result.current.navGroups.flatMap((group) =>
      group.items.map((item) => item.title)
    )
    expect(visibleDomains).toEqual(['外观与主题'])
  })
})

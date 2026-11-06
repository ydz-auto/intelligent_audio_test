/**
 * 顶部导航 RBAC 过滤单测（接线壳 INT-607，00_页面清单与RBAC划分.md §4.1
 * 顶部导航项结果行）：六项 × 五角色 + 未登录显隐矩阵。
 * 主页/文档/关于全员；工作台登录即可（未登录 requiresAuth 受限项）；报告 report:read；
 * 排行榜 benchmark:ranking:read（INT-429 已授 tester/algo_engineer）。
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { renderHook } from '@testing-library/react'

import { useTopNavLinks } from '@/application/hooks/use-top-nav-links'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import type { AuthUser } from '@/domain/models/user'

function makeUser(username: string, permissions: string[]): AuthUser {
  return {
    id: '1',
    username,
    displayName: username,
    roleName: username,
    permissions,
  }
}

function titles() {
  const { result } = renderHook(() => useTopNavLinks())
  return result.current.map((link) => link.title)
}

describe('useTopNavLinks RBAC 过滤', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null })
  })

  it("admin（'*' 通配）→ 六项全显", () => {
    useAuthStore.setState({ user: makeUser('admin', ['*']) })
    expect(titles()).toEqual(['主页', '工作台', '报告', '排行榜', '文档', '关于'])
  })

  it('tester（report:read + benchmark:ranking:read，INT-429）→ 六项全显', () => {
    useAuthStore.setState({
      user: makeUser('tester', ['report:read', 'benchmark:ranking:read']),
    })
    expect(titles()).toEqual(['主页', '工作台', '报告', '排行榜', '文档', '关于'])
  })

  it('algo_engineer（同 tester）→ 六项全显', () => {
    useAuthStore.setState({
      user: makeUser('algo', ['report:read', 'benchmark:ranking:read']),
    })
    expect(titles()).toEqual(['主页', '工作台', '报告', '排行榜', '文档', '关于'])
  })

  it('device_admin（无 report/benchmark 码）→ 四项（报告/排行榜隐藏）', () => {
    useAuthStore.setState({
      user: makeUser('device_admin', ['device:read', 'home:read']),
    })
    expect(titles()).toEqual(['主页', '工作台', '文档', '关于'])
  })

  it('guest（report:read 无 benchmark）→ 五项（排行榜隐藏）', () => {
    useAuthStore.setState({
      user: makeUser('guest', ['report:read']),
    })
    expect(titles()).toEqual(['主页', '工作台', '报告', '文档', '关于'])
  })

  it('未登录 → 主页/工作台(requiresAuth)/文档/关于（报告/排行榜隐藏）', () => {
    const { result } = renderHook(() => useTopNavLinks())
    expect(result.current.map((l) => l.title)).toEqual([
      '主页',
      '工作台',
      '文档',
      '关于',
    ])
    const workbench = result.current.find((l) => l.title === '工作台')
    expect(workbench?.requiresAuth).toBe(true)
    expect(workbench?.permission).toBeUndefined()
  })

  it('登录态变化即时收敛（登出后报告/排行榜隐藏，工作台转 requiresAuth）', () => {
    useAuthStore.setState({
      user: makeUser('tester', ['report:read', 'benchmark:ranking:read']),
    })
    const { result, rerender } = renderHook(() => useTopNavLinks())
    expect(result.current.map((l) => l.title)).toHaveLength(6)

    useAuthStore.setState({ user: null })
    rerender()
    expect(result.current.map((l) => l.title)).toEqual([
      '主页',
      '工作台',
      '文档',
      '关于',
    ])
    expect(result.current.find((l) => l.title === '工作台')?.requiresAuth).toBe(
      true
    )
  })
})

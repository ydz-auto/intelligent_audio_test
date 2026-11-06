import { describe, expect, it } from 'vitest'

import {
  canSeeChangePassword,
  canSeeFavoriteReports,
  canSeeFavoriteTasks,
  canSeeFavoriteTestcases,
  canSeeMyReports,
  canSeeMyTasks,
  canSeeSettingsQuickLink,
  type PermissionUser,
} from '@/application/profile/permission-gate'

const WILDCARD: PermissionUser = { permissions: ['*'] }
const GUEST: PermissionUser = { permissions: ['report:read'] }
const DEVICE_ADMIN: PermissionUser = { permissions: ['report:read', 'device:read'] }
const TESTER: PermissionUser = {
  permissions: ['task:read', 'report:read', 'testcase:read', 'log:manage'],
}
const EMPTY: PermissionUser = { permissions: [] }
const NULL_USER: PermissionUser = null

describe('permission-gate（13_个人中心.md §4.2 区块可见性）', () => {
  it('我的任务格：task:read 门槛，guest 无 task:read 隐藏', () => {
    expect(canSeeMyTasks(TESTER)).toBe(true)
    expect(canSeeMyTasks(GUEST)).toBe(false)
    expect(canSeeMyTasks(DEVICE_ADMIN)).toBe(false)
    expect(canSeeMyTasks(WILDCARD)).toBe(true)
    expect(canSeeMyTasks(NULL_USER)).toBe(false)
  })

  it('我的报告格：report:read 门槛，device_admin 有 report:read 可见', () => {
    expect(canSeeMyReports(TESTER)).toBe(true)
    expect(canSeeMyReports(GUEST)).toBe(true)
    expect(canSeeMyReports(DEVICE_ADMIN)).toBe(true)
    expect(canSeeMyReports(EMPTY)).toBe(false)
    expect(canSeeMyReports(NULL_USER)).toBe(false)
  })

  it('收藏明细行按实体 read 码过滤：device_admin 只见报告行', () => {
    expect(canSeeFavoriteTasks(DEVICE_ADMIN)).toBe(false)
    expect(canSeeFavoriteReports(DEVICE_ADMIN)).toBe(true)
    expect(canSeeFavoriteTestcases(DEVICE_ADMIN)).toBe(false)

    expect(canSeeFavoriteTasks(GUEST)).toBe(false)
    expect(canSeeFavoriteReports(GUEST)).toBe(true)
    expect(canSeeFavoriteTestcases(GUEST)).toBe(false)
  })

  it('系统设置快捷行：设置域权限四码任一命中；tester 经 log:manage 可见（INT-417）', () => {
    expect(canSeeSettingsQuickLink(TESTER)).toBe(true)
    expect(canSeeSettingsQuickLink(DEVICE_ADMIN)).toBe(false)
    expect(canSeeSettingsQuickLink(GUEST)).toBe(false)
    expect(canSeeSettingsQuickLink(WILDCARD)).toBe(true)
    expect(canSeeSettingsQuickLink(NULL_USER)).toBe(false)
  })

  it('修改密码入口：后端端点未落，五角色恒隐藏（§3.5.1/§4.3-1，含 AUTH_MODE=off 通配）', () => {
    expect(canSeeChangePassword()).toBe(false)
  })
})

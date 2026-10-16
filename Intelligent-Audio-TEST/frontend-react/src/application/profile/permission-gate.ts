/**
 * 个人中心区块可见性纯函数（application 层，13_个人中心.md §4.2/§7）：
 * 页面内权限不 redirect，只隐藏区块（对齐 newAPI「隐藏而非置灰」）。
 * 口径（与 domain hasPermission 通配逻辑同源）：
 *  - 「我的任务」格 → task:read，不满足整格隐藏
 *  - 「我的报告」格 → report:read，不满足整格隐藏
 *  - 收藏明细行 → 按实体 read 码 task:read / report:read / testcase:read
 *  - 「系统设置」快捷行 → hasAnyPermission(SYSTEM_SETTINGS_PERMISSIONS)
 *  - 「修改密码」入口 → 后端端点未落，五角色均隐藏（能力缺口，§4.3-1）
 */
import { SYSTEM_SETTINGS_PERMISSIONS } from '@/domain/models/user'

export type PermissionUser = { permissions: string[] } | null

/** 权限码判定（'*' 通配直通；与 domain hasPermission 同源，避免引入整 AuthUser 耦合） */
function hasCode(user: PermissionUser, permission: string): boolean {
  if (!user) return false
  if (user.permissions.includes('*')) return true
  return user.permissions.includes(permission)
}

/** 我的任务格（task:read） */
export function canSeeMyTasks(user: PermissionUser): boolean {
  return hasCode(user, 'task:read')
}

/** 我的报告格（report:read） */
export function canSeeMyReports(user: PermissionUser): boolean {
  return hasCode(user, 'report:read')
}

/** 收藏明细-任务行（task:read） */
export function canSeeFavoriteTasks(user: PermissionUser): boolean {
  return hasCode(user, 'task:read')
}

/** 收藏明细-报告行（report:read） */
export function canSeeFavoriteReports(user: PermissionUser): boolean {
  return hasCode(user, 'report:read')
}

/** 收藏明细-用例行（testcase:read） */
export function canSeeFavoriteTestcases(user: PermissionUser): boolean {
  return hasCode(user, 'testcase:read')
}

/** 「系统设置」快捷行（任一设置域权限；INT-417 收窄四码） */
export function canSeeSettingsQuickLink(user: PermissionUser): boolean {
  return SYSTEM_SETTINGS_PERMISSIONS.some((code) => hasCode(user, code))
}

/** 「修改密码」入口：后端端点未落，恒隐藏（§3.5.1/§4.3-1；AUTH_MODE=off 也隐藏） */
export function canSeeChangePassword(): boolean {
  return false
}

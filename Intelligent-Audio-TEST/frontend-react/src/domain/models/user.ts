/**
 * 用户与会话领域模型（domain 层）。
 * 形态对照 api_gateway/schemas 的用户/权限字段；mock 会话与真实接口对齐，
 * 后续接线时字段不返工（红线④）。
 */

export type AuthUser = {
  id: string
  username: string
  displayName: string
  roleName: string
  /** 权限码集合；'*' 为超级通配 */
  permissions: string[]
  avatarUrl?: string
}

export const WILDCARD_PERMISSION = '*'

export function hasPermission(
  user: AuthUser | null,
  permission: string
): boolean {
  if (!user) return false
  if (user.permissions.includes(WILDCARD_PERMISSION)) return true
  return user.permissions.includes(permission)
}

export function hasAnyPermission(
  user: AuthUser | null,
  permissions: string[]
): boolean {
  return permissions.some((permission) => hasPermission(user, permission))
}

/**
 * 系统设置工作区入口判定所需的权限码集合（INT-347 §3.2 定稿，INT-417 收窄后四码）：
 * `algorithm:definition_manage`/`evaluation:dim_manage`/`tag:create`/`spl:create`/
 * `digital_spl:create` 五码随「算法配置」「测试配置」两域移出守卫集合。
 */
export const SYSTEM_SETTINGS_PERMISSIONS = [
  'user:read',
  'role:read',
  'auth:manage_provider',
  'log:manage',
] as const

/**
 * 平台用户（用户与角色权限管理域，INT-347 §2.0/§4.4.1）。
 * 形态对照 user_bp.py 契约：角色/附加权限/状态；`roleName` 与附加权限码用于
 * 用户表与权限矩阵渲染，后续接线不返工。
 */
export type PlatformUserStatus = 'active' | 'disabled' | 'locked'

export type PlatformUser = {
  id: string
  username: string
  displayName: string
  email: string
  /** 归属角色 code（admin/tester/algo_engineer/device_admin/guest） */
  roleCode: string
  roleName: string
  status: PlatformUserStatus
  /** 生效权限码集合（角色基线 ∪ 附加 overrides 合并去重；列表口径） */
  permissions: string[]
  /** 附加权限码（grant/revoke overrides，角色权限之上；详情查询返回） */
  extraPermissions: string[]
  createdAt: string
}

export const USER_STATUS_META: Record<
  PlatformUserStatus,
  { label: string }
> = {
  active: { label: '正常' },
  disabled: { label: '停用' },
  locked: { label: '锁定' },
}

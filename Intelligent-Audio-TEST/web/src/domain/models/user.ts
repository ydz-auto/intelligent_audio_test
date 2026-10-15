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

/** 系统设置入口判定所需的权限码集合（04_控制台.md §3.2，对齐 INT-347 §2.1） */
export const SYSTEM_SETTINGS_PERMISSIONS = [
  'user:read',
  'auth:manage_provider',
  'algorithm:definition_manage',
  'evaluation:dim_manage',
  'tag:create',
  'spl:create',
  'digital_spl:create',
] as const

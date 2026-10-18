/**
 * 用户 DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换层）。
 * 对照 api_gateway user_bp.py + auth_service `_user_to_dict` 响应契约：
 * GET /users → { items: [...], total, page, per_page, pages }，user dict：
 * { id, username, display_name, email, role_id, role_name, status, is_active,
 *   permissions, oauth_provider, oauth_subject, created_at, updated_at,
 *   last_login_at }；
 * GET /users/{id} 详情额外带 overrides: [{ permission_id, code, granted }]。
 * 注意：列表响应不含 overrides（附加权限需详情端点），列表 extraPermissions 置空
 * （INT-651 接线证据：后端缺口 → 详情端点承载，列表列显示受限于此）。
 * display_name 后端已支持（INT-697 落地，INT-698 接线），未设置/清空时为 null，
 * toPlatformUser 兜底 username。
 */
import { ROLE_META, type RoleCode } from '@/domain/models/role'
import type { PlatformUser, PlatformUserStatus } from '@/domain/models/user'

export interface UserOverrideDto {
  permission_id: number
  code: string
  granted: boolean
}

export interface UserDto {
  id: number
  username: string
  display_name?: string | null
  email: string
  role_id: number | null
  role_name: string
  status: string
  is_active: boolean
  permissions: string[]
  oauth_provider?: string | null
  oauth_subject?: string | null
  created_at?: string | null
  updated_at?: string | null
  last_login_at?: string | null
  overrides?: UserOverrideDto[]
}

export interface UserListResultDto {
  items: UserDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** 后端状态 → 前端状态（inactive=停用；deleted 已被列表排除） */
export function toPlatformUserStatus(status: string): PlatformUserStatus {
  if (status === 'inactive') return 'disabled'
  if (status === 'locked') return 'locked'
  return 'active'
}

/** 前端状态 → 后端状态（disabled=停用 → inactive） */
export function toBackendStatus(status: PlatformUserStatus): string {
  if (status === 'disabled') return 'inactive'
  return status
}

/** 后端 user dict → Domain PlatformUser（display_name 为空/null 时兜底 username） */
export function toPlatformUser(raw: UserDto): PlatformUser {
  const roleCode = raw.role_name ?? ''
  return {
    id: String(raw.id),
    username: raw.username ?? '',
    displayName: raw.display_name ?? raw.username ?? '',
    email: raw.email ?? '',
    roleCode,
    roleName: ROLE_META[roleCode as RoleCode]?.name ?? roleCode,
    status: toPlatformUserStatus(raw.status),
    extraPermissions: (raw.overrides ?? [])
      .filter((override) => override.granted)
      .map((override) => override.code),
    createdAt: raw.created_at ?? '',
  }
}

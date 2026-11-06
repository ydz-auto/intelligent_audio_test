/**
 * 用户/角色/权限 DTO（infrastructure 层，INT-729 接线）。
 * 契约对照 api_gateway/routes/user_bp.py + role_bp.py + auth_service
 * servicers._user_to_dict/_role_to_dict/_permission_to_dict 实测：
 * - GET /auth/users?page=&page_size=&status=&keyword=&role_id= →
 *   { items, total, page, per_page, pages }（INT-297 分页信封）
 * - GET /auth/users/{id} → 单用户（含 overrides 明细）
 * - GET /auth/roles → { roles }；GET /auth/permissions → { permissions }
 * snake_case → camelCase 收敛于 adapters/dto/iam-adapter。
 */

export type AuthUserDto = {
  id: number
  username: string
  email: string | null
  role_id: number
  role_name: string
  status: string
  is_active: boolean
  /** 生效权限码集合（角色基线 ∪ 附加 overrides 合并去重） */
  permissions: string[]
  oauth_provider: string | null
  oauth_subject: string | null
  display_name: string | null
  created_at: string
  updated_at: string
  last_login_at: string
  /** 详情查询追加：附加权限 override 明细 [{permission_id, code, granted}] */
  overrides?: Array<{
    permission_id: number
    code: string
    granted: boolean
  }>
}

export type UsersPageDto = {
  items: AuthUserDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

export type AuthRoleDto = {
  id: number
  name: string
  description: string
  permissions: string[]
  is_system: boolean
}

export type RolesPageDto = {
  roles: AuthRoleDto[]
}

export type AuthPermissionDto = {
  id: number
  /** 权限码（如 task:read） */
  name: string
  /** 中文描述 */
  description: string
}

export type PermissionsPageDto = {
  permissions: AuthPermissionDto[]
}

/** OAuth 提供方管理端形态（auth_service to_admin_dict：client_secret 掩去） */
export type OAuthProviderAdminDto = {
  id: number
  name: string
  slug: string
  icon: string
  enabled: boolean
  client_id: string
  has_client_secret: boolean
  authorize_url: string
  token_url: string
  userinfo_url: string
  scopes: string
  user_id_field: string
  username_field: string
  display_name_field: string
  email_field: string
  created_at: string
  updated_at: string
}

export type OAuthProvidersPageDto = {
  providers: OAuthProviderAdminDto[]
}

export type OAuthDiscoveryDto = {
  well_known_url: string
  discovery: {
    authorization_endpoint?: string
    token_endpoint?: string
    userinfo_endpoint?: string
    [key: string]: unknown
  }
}

/** 系统选项 KV 通道（根级挂载 /api/option/，无 /api/v1 前缀） */
export type SystemOptionsDto = Record<string, string | number | boolean | string[] | null>

/** 日志归档状态（log_query_service.get_archive_status 实测形态） */
export type LogArchiveStatusDto = {
  totalLogs: number
  hotLogs: number
  coldLogs: number
  archiveDir: string
  taskArchives: number
  caseArchives: number
  otherArchives: number
}

export type LogArchiveResultDto = {
  archived_count: number
  deleted_count: number
  archive_file: string | null
  remaining_count: number
}

export type LogClearResultDto = {
  deletedCount: number
}

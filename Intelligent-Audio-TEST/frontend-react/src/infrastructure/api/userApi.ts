/**
 * 用户管理真实 API（infrastructure/api 层；接线 INT-651）。
 * 对照 api_gateway user_bp.py 契约（全部挂 /api/v1/auth 前缀）：
 * GET /users（分页 ≤100 + status/keyword/role_id 过滤）、GET /users/{id}（详情含
 * overrides 附加权限明细）、POST /users、PUT /users/{id}、POST /users/{id}/role、
 * POST /users/{id}/permissions（单条授予）、DELETE /users/{id}/permissions/{permission_id}、
 * DELETE /users/{id}。
 * 说明：displayName 走后端 display_name 字段（INT-697 落地，INT-698 接线），
 * 未设置/清空为 null 时 DTO 兜底 username；列表响应不含 overrides（附加权限
 * 需详情端点承载）；角色分配按 role_id（前端 roleCode → role_id 由调用方解析）。
 */
import type { PlatformUser, PlatformUserStatus } from '@/domain/models/user'
import { apiClient } from '@/infrastructure/api/client'
import {
  toBackendStatus,
  toPlatformUser,
  type UserDto,
  type UserListResultDto,
} from '@/infrastructure/dto/user.dto'

export const USERS_QUERY_KEY = ['iam', 'users'] as const

export type UserListFilter = {
  keyword?: string
  status?: PlatformUserStatus | 'all'
  /** 多选角色码（FacetedFilter 多选口径；后端仅支持单 role_id，多选在 API 层按 role_name 过滤） */
  roleCodes?: string[]
}

/**
 * 用户列表（GET /auth/users；status/keyword 交后端，多选角色按 role_name 过滤——
 * 后端仅单 role_id，列表 ≤100 窗口内过滤保持 FacetedFilter 多选语义）。
 */
export async function getUsers(filter: UserListFilter = {}): Promise<PlatformUser[]> {
  const params: Record<string, unknown> = { page: 1, page_size: 100 }
  if (filter.keyword) params.keyword = filter.keyword
  if (filter.status && filter.status !== 'all') {
    params.status = toBackendStatus(filter.status)
  }
  const data = await apiClient.get<UserListResultDto>('/auth/users', { params })
  let users = (data.items ?? []).map(toPlatformUser)
  if (filter.roleCodes && filter.roleCodes.length > 0) {
    const codes = new Set(filter.roleCodes)
    users = users.filter((user) => codes.has(user.roleCode))
  }
  return users
}

/** 用户详情（GET /auth/users/{id}；overrides → extraPermissions，供抽屉回填） */
export async function getUser(userId: string): Promise<PlatformUser> {
  const data = await apiClient.get<UserDto>(`/auth/users/${userId}`)
  return toPlatformUser(data)
}

/** 创建用户（POST /auth/users；role_id 由调用方按 roleCode 解析，缺省 0=默认角色） */
export async function createUser(input: {
  username: string
  displayName?: string
  email: string
  password: string
  roleId?: number
  status: PlatformUserStatus
}): Promise<PlatformUser> {
  const body: Record<string, unknown> = {
    username: input.username,
    email: input.email,
    password: input.password,
    role_id: input.roleId ?? 0,
  }
  if (input.displayName !== undefined) body.display_name = input.displayName
  const data = await apiClient.post<{ user_id?: number }>('/auth/users', body)
  return {
    id: data.user_id != null ? String(data.user_id) : `user-${Date.now()}`,
    username: input.username,
    displayName: input.displayName || input.username,
    email: input.email,
    roleCode: '',
    roleName: '',
    status: input.status,
    permissions: [],
    extraPermissions: [],
    createdAt: new Date().toISOString(),
  }
}

/**
 * 更新用户（PUT /auth/users/{id}；email/status/displayName 落库，displayName
 * 缺省键不发送——编辑态未改显示名时保留原值；显式传空串则清空后端 display_name）。
 * password 非空时随 PUT 提交改密（后端已支持，INT-1584）；留空/缺省不带该键，
 * 保持「留空表示不修改密码」。
 */
export type UserUpdatePatch = Partial<
  Pick<PlatformUser, 'displayName' | 'email' | 'status' | 'roleCode' | 'roleName'>
> & {
  /** 新密码（8–128 位）；空串视为不修改 */
  password?: string
}

export async function updateUser(
  userId: string,
  patch: UserUpdatePatch
): Promise<PlatformUser> {
  const body: Record<string, unknown> = {}
  if (patch.displayName !== undefined) body.display_name = patch.displayName
  if (patch.email !== undefined) body.email = patch.email
  if (patch.status !== undefined) body.status = toBackendStatus(patch.status)
  if (patch.password) body.password = patch.password
  await apiClient.put(`/auth/users/${userId}`, body)
  return {
    id: userId,
    username: '',
    displayName: patch.displayName ?? '',
    email: patch.email ?? '',
    roleCode: patch.roleCode ?? '',
    roleName: patch.roleName ?? '',
    status: patch.status ?? 'active',
    permissions: [],
    extraPermissions: [],
    createdAt: '',
  }
}

/** 删除/软删除用户（DELETE /auth/users/{id}；不可删自己由后端 403 兜底） */
export async function deleteUser(userId: string): Promise<void> {
  await apiClient.delete(`/auth/users/${userId}`)
}

/** 分配用户角色（POST /auth/users/{id}/role；role_id 必填） */
export async function assignRole(userId: string, roleId: number): Promise<void> {
  await apiClient.post(`/auth/users/${userId}/role`, { role_id: roleId })
}

/**
 * 授予/撤销用户附加权限（差量同步目标权限码集合）：
 * 以详情 overrides（granted=true 的 permission_id）为基线——新增码逐条 POST
 * /users/{id}/permissions，撤销码按 permission_id DELETE /users/{id}/permissions/{id}。
 */
export async function grantPermissions(
  userId: string,
  permissions: string[]
): Promise<void> {
  const detail = await apiClient.get<UserDto>(`/auth/users/${userId}`)
  const current = (detail.overrides ?? []).filter((override) => override.granted)
  const currentCodes = new Set(current.map((override) => override.code))
  const target = new Set(permissions)

  for (const code of permissions) {
    if (!currentCodes.has(code)) {
      await apiClient.post(`/auth/users/${userId}/permissions`, { permission: code })
    }
  }
  for (const override of current) {
    if (!target.has(override.code)) {
      await apiClient.delete(
        `/auth/users/${userId}/permissions/${override.permission_id}`
      )
    }
  }
}

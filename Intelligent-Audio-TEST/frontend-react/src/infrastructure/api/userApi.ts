/**
 * 用户管理 API（infrastructure 层，INT-729 接线）。
 * 契约对照 api_gateway/routes/user_bp.py + auth_service servicers 实测：
 * GET /auth/users（分页 ≤100 + status/keyword/role_id 过滤）→ {items,total,page,per_page,pages}；
 * GET /auth/users/{id}（含 overrides 明细）；POST /auth/users（role_id 选填）；
 * PUT /auth/users/{id}（键缺省=不修改，display_name 空串=清空）；
 * DELETE /auth/users/{id}；POST /auth/users/{id}/role（{role_id}）；
 * POST /auth/users/{id}/permissions（{permission} 单码授予）+
 * DELETE /auth/users/{id}/permissions/{permission_id}（差量撤销）。
 * 权限门槛 user:read/create/update/delete/assign_role/grant_permission。
 * snake_case → camelCase 收敛于 iam-adapter；页面只消费 camelCase 领域对象。
 */
import { apiClient } from './client'
import { getPermissionCatalog, getRoles } from './roleApi'
import type { PlatformUser, PlatformUserStatus } from '@/domain/models/user'
import {
  toBackendUserStatus,
  toPlatformUser,
} from '@/infrastructure/adapters/dto/iam-adapter'
import type { AuthUserDto, UsersPageDto } from '@/infrastructure/dto/iam.dto'

export const USERS_QUERY_KEY = ['iam', 'users'] as const

export type UserListFilter = {
  keyword?: string
  status?: PlatformUserStatus | 'all'
  /** 多选角色码（FacetedFilter 多选口径；后端 role_id 单值，客户端二次过滤） */
  roleCodes?: string[]
}

/** 分页拉取全部匹配用户（per_page=100 上限，total/pages 翻页兜底） */
async function fetchAllUsers(params: {
  status?: string
  keyword?: string
}): Promise<AuthUserDto[]> {
  const perPage = 100
  let page = 1
  const all: AuthUserDto[] = []
  for (;;) {
    const dto = await apiClient.get<UsersPageDto>('/auth/users', {
      params: {
        page,
        page_size: perPage,
        status: params.status || undefined,
        keyword: params.keyword || undefined,
      },
    })
    const items = dto.items ?? []
    all.push(...items)
    const total = dto.total ?? all.length
    const pages = dto.pages ?? Math.ceil(total / perPage)
    if (page >= pages || items.length === 0) break
    page += 1
  }
  return all
}

export async function getUsers(filter: UserListFilter = {}): Promise<PlatformUser[]> {
  const status =
    filter.status && filter.status !== 'all'
      ? toBackendUserStatus(filter.status)
      : undefined
  const all = await fetchAllUsers({ status, keyword: filter.keyword })
  return all
    .map(toPlatformUser)
    .filter((user) => {
      if (
        filter.roleCodes &&
        filter.roleCodes.length > 0 &&
        !filter.roleCodes.includes(user.roleCode)
      ) {
        return false
      }
      return true
    })
}

/** 用户详情（含 overrides 附加权限明细；编辑抽屉回填基线） */
export async function getUserDetail(userId: string): Promise<PlatformUser> {
  const dto = await apiClient.get<AuthUserDto>(`/auth/users/${userId}`)
  return toPlatformUser(dto)
}

export async function createUser(input: {
  username: string
  displayName?: string
  email: string
  password: string
  roleId?: number
  status: PlatformUserStatus
}): Promise<void> {
  const body: Record<string, unknown> = {
    username: input.username,
    email: input.email,
    password: input.password,
  }
  if (input.displayName) body.display_name = input.displayName
  if (input.roleId) body.role_id = input.roleId
  await apiClient.post('/auth/users', body)
}

export async function updateUser(
  userId: string,
  patch: Partial<Pick<PlatformUser, 'displayName' | 'email' | 'status'>>
): Promise<void> {
  const body: Record<string, unknown> = {}
  if ('displayName' in patch) body.display_name = patch.displayName ?? ''
  if ('email' in patch) body.email = patch.email ?? ''
  if ('status' in patch && patch.status) {
    body.status = toBackendUserStatus(patch.status)
  }
  await apiClient.put(`/auth/users/${userId}`, body)
}

export async function deleteUser(userId: string): Promise<void> {
  await apiClient.delete(`/auth/users/${userId}`)
}

export async function assignRole(
  userId: string,
  roleCode: string
): Promise<void> {
  const roles = await getRoles()
  const role = roles.find((r) => r.code === roleCode)
  if (!role) throw new Error(`角色不存在：${roleCode}`)
  await apiClient.post(`/auth/users/${userId}/role`, {
    role_id: Number(role.id),
  })
}

/**
 * 全量替换用户附加权限（差量同步：新增逐码 POST 授予，移除按权限点 ID
 * DELETE 撤销——后端单码授予/差量撤销语义，用户_bp.py:66-77 实测）。
 */
export async function grantPermissions(
  userId: string,
  permissions: string[],
  previousPermissions: string[] = []
): Promise<void> {
  const added = permissions.filter((p) => !previousPermissions.includes(p))
  const removed = previousPermissions.filter((p) => !permissions.includes(p))
  const catalog = await getPermissionCatalog()
  const idByCode = new Map<string, number>()
  for (const module of catalog) {
    for (const permission of module.permissions) {
      if (permission.id != null) idByCode.set(permission.code, permission.id)
    }
  }
  await Promise.all([
    ...added.map((code) =>
      apiClient.post(`/auth/users/${userId}/permissions`, { permission: code })
    ),
    ...removed.map((code) => {
      const permissionId = idByCode.get(code)
      return permissionId
        ? apiClient.delete(`/auth/users/${userId}/permissions/${permissionId}`)
        : Promise.resolve()
    }),
  ])
}

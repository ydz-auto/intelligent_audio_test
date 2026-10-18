/**
 * 角色管理真实 API（infrastructure/api 层；接线 INT-651）。
 * 对照 api_gateway role_bp.py 契约（全部挂 /api/v1/auth 前缀）：
 * GET /roles（role:read，回 permissions 码列表 + is_system）、GET /permissions
 * （permission:read，权限点目录只读）、POST/PUT/DELETE /roles（role:create/update/delete）、
 * POST /roles/{id}/permissions 全量替换（admin 角色的 '*' 不可移除由后端 400 兜底）。
 * 约束语义：系统角色删除后端 400、被用户引用 409——前端提交后由 ApiError.userMessage 呈现。
 */
import type { PermissionModule } from '@/domain/models/permission'
import type { PlatformRole } from '@/domain/models/role'
import { apiClient } from '@/infrastructure/api/client'
import {
  toPermissionModules,
  toPlatformRole,
  type PermissionDto,
  type PermissionsResultDto,
  type RoleDto,
  type RolesResultDto,
} from '@/infrastructure/dto/role.dto'
import type { UserListResultDto } from '@/infrastructure/dto/user.dto'

export const ROLES_QUERY_KEY = ['iam', 'roles'] as const
export const PERMISSION_CATALOG_QUERY_KEY = ['iam', 'permission-catalog'] as const

/**
 * 全部角色列表（role:read）。后端角色 dict 不含 user_count——以用户列表分页计数补全：
 * GET /auth/users 单页 ≤100，按响应 `pages` 逐页拉取聚合，避免用户数 >100 时「用户数」
 * 列欠计（P3-2）；失败回退 0 不影响角色列表，仅该列展示受限于此。
 */
export async function getRoles(): Promise<PlatformRole[]> {
  const data = await apiClient.get<RolesResultDto>('/auth/roles')
  const roles = (data.roles ?? []).map(toPlatformRole)
  try {
    const counts = new Map<number, number>()
    const pageSize = 100
    let page = 1
    let pages = 1
    do {
      const users = await apiClient.get<UserListResultDto>('/auth/users', {
        params: { page, page_size: pageSize },
      })
      for (const user of users.items ?? []) {
        if (user.role_id != null) {
          counts.set(user.role_id, (counts.get(user.role_id) ?? 0) + 1)
        }
      }
      pages = users.pages ?? 1
      page += 1
    } while (page <= pages)
    return roles.map((role) => ({
      ...role,
      userCount: counts.get(Number(role.id)) ?? 0,
    }))
  } catch {
    return roles
  }
}

/** 权限点目录（permission:read；后端扁平返回，模块分组在 DTO 层重建） */
export async function getPermissionCatalog(): Promise<PermissionModule[]> {
  const data = await apiClient.get<PermissionsResultDto>('/auth/permissions')
  return toPermissionModules(data.permissions ?? [])
}

/** 创建自定义角色（POST /auth/roles → { role_id }；权限码入参 permission_codes） */
export async function createRole(input: {
  name: string
  description: string
  permissions: string[]
}): Promise<PlatformRole> {
  const data = await apiClient.post<{ role_id?: number }>('/auth/roles', {
    name: input.name,
    description: input.description,
    permission_codes: input.permissions,
  })
  return {
    id: data.role_id != null ? String(data.role_id) : `role-${Date.now()}`,
    code: input.name,
    name: input.name,
    description: input.description,
    isSystem: false,
    permissions: input.permissions,
    userCount: 0,
  }
}

/** 更新角色信息（PUT /auth/roles/{id}；name/description 空串=不修改，由后端兜底） */
export async function updateRole(
  roleId: string,
  patch: Partial<Pick<PlatformRole, 'name' | 'description'>>
): Promise<PlatformRole> {
  await apiClient.put(`/auth/roles/${roleId}`, {
    name: patch.name ?? '',
    description: patch.description ?? '',
  })
  return {
    id: roleId,
    code: patch.name ?? '',
    name: patch.name ?? '',
    description: patch.description ?? '',
    isSystem: false,
    permissions: [],
    userCount: 0,
  }
}

/** 全量替换角色权限（POST /auth/roles/{id}/permissions；admin '*' 不可移除由后端 400） */
export async function setRolePermissions(
  roleId: string,
  permissions: string[]
): Promise<void> {
  await apiClient.post(`/auth/roles/${roleId}/permissions`, {
    permission_codes: permissions,
  })
}

/** 删除角色（DELETE /auth/roles/{id}；系统角色 400 / 被引用 409 抛 ApiError） */
export async function deleteRole(roleId: string): Promise<void> {
  await apiClient.delete(`/auth/roles/${roleId}`)
}

/** @deprecated 接线后不再使用 mock；仅保留类型占位避免误导入 */
export type { PermissionDto, PermissionsResultDto, RoleDto, RolesResultDto }

/**
 * 角色/权限点 API（infrastructure 层，INT-729 接线）。
 * 契约对照 api_gateway/routes/role_bp.py + auth_service servicers 实测：
 * GET /auth/roles → {roles:[{id,name,description,permissions,is_system}]}；
 * GET /auth/permissions → {permissions:[{id,name(权限码),description(中文)}]}
 * （权限点仅只读暴露）；POST /auth/roles（{name,description,permission_codes}）、
 * PUT /auth/roles/{id}（空串=不修改）、POST /auth/roles/{id}/permissions
 * （全量替换）、DELETE /auth/roles/{id}（系统角色 400、被引用 409）。
 * 权限门槛 role:read/create/update/delete + permission:read。
 * snake_case → camelCase 收敛于 iam-adapter。
 */
import { apiClient } from './client'
import type { PlatformRole } from '@/domain/models/role'
import type { PermissionModule } from '@/domain/models/permission'
import {
  toPermissionModules,
  toPlatformRole,
} from '@/infrastructure/adapters/dto/iam-adapter'
import type {
  PermissionsPageDto,
  RolesPageDto,
} from '@/infrastructure/dto/iam.dto'

export const ROLES_QUERY_KEY = ['iam', 'roles'] as const
export const PERMISSION_CATALOG_QUERY_KEY = ['iam', 'permission-catalog'] as const

export async function getRoles(): Promise<PlatformRole[]> {
  const dto = await apiClient.get<RolesPageDto>('/auth/roles')
  return (dto.roles ?? []).map(toPlatformRole)
}

export async function getPermissionCatalog(): Promise<PermissionModule[]> {
  const dto = await apiClient.get<PermissionsPageDto>('/auth/permissions')
  return toPermissionModules(dto.permissions ?? [])
}

export async function createRole(input: {
  name: string
  description: string
  permissions: string[]
}): Promise<void> {
  await apiClient.post('/auth/roles', {
    name: input.name,
    description: input.description,
    permission_codes: input.permissions,
  })
}

export async function updateRole(
  roleId: string,
  patch: { name?: string; description?: string }
): Promise<void> {
  const body: Record<string, unknown> = {}
  if (patch.name !== undefined) body.name = patch.name
  if (patch.description !== undefined) body.description = patch.description
  await apiClient.put(`/auth/roles/${roleId}`, body)
}

export async function setRolePermissions(
  roleId: string,
  permissions: string[]
): Promise<void> {
  await apiClient.post(`/auth/roles/${roleId}/permissions`, {
    permission_codes: permissions,
  })
}

export async function deleteRole(roleId: string): Promise<void> {
  await apiClient.delete(`/auth/roles/${roleId}`)
}

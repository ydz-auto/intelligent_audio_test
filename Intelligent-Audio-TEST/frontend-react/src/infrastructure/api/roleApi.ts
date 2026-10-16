/**
 * 角色管理 API 桩（infrastructure 层，红线④：mock 常量）。
 * 契约对照 role_bp.py 实测（INT-30 已落，INT-347 §2.0）：
 * GET /roles[/{id}]、GET /permissions（权限点仅只读暴露）、POST/PUT/DELETE /roles、
 * POST /roles/{id}/permissions（全量替换）；权限门槛 role:read/create/update/delete + permission:read。
 * 约束：admin 的 `*` 不可移除（role_bp.py:56）、系统角色不可删、被用户引用 409。
 */
import { MOCK_PERMISSION_CATALOG } from '@/infrastructure/mock/iam-mock'
import type { PermissionModule } from '@/domain/models/permission'
import type { PlatformRole } from '@/domain/models/role'

export const ROLES_QUERY_KEY = ['iam', 'roles'] as const
export const PERMISSION_CATALOG_QUERY_KEY = ['iam', 'permission-catalog'] as const

export async function getRoles(): Promise<PlatformRole[]> {
  const { MOCK_PLATFORM_ROLES } = await import('@/infrastructure/mock/iam-mock')
  return MOCK_PLATFORM_ROLES
}

export async function getPermissionCatalog(): Promise<PermissionModule[]> {
  return MOCK_PERMISSION_CATALOG
}

export async function createMockRole(input: {
  name: string
  description: string
  permissions: string[]
}): Promise<PlatformRole> {
  const { MOCK_PLATFORM_ROLES } = await import('@/infrastructure/mock/iam-mock')
  const role: PlatformRole = {
    id: `role-${Date.now()}`,
    code: `custom_${Date.now().toString(36)}`,
    name: input.name,
    description: input.description,
    isSystem: false,
    permissions: input.permissions,
    userCount: 0,
  }
  MOCK_PLATFORM_ROLES.push(role)
  return role
}

export async function updateMockRole(
  roleId: string,
  patch: Partial<Pick<PlatformRole, 'name' | 'description'>>
): Promise<PlatformRole> {
  const { MOCK_PLATFORM_ROLES } = await import('@/infrastructure/mock/iam-mock')
  const index = MOCK_PLATFORM_ROLES.findIndex((role) => role.id === roleId)
  if (index === -1) throw new Error(`角色不存在：${roleId}`)
  MOCK_PLATFORM_ROLES[index] = { ...MOCK_PLATFORM_ROLES[index], ...patch }
  return MOCK_PLATFORM_ROLES[index]
}

export async function setMockRolePermissions(
  roleId: string,
  permissions: string[]
): Promise<void> {
  const { MOCK_PLATFORM_ROLES } = await import('@/infrastructure/mock/iam-mock')
  const index = MOCK_PLATFORM_ROLES.findIndex((role) => role.id === roleId)
  if (index === -1) throw new Error(`角色不存在：${roleId}`)
  MOCK_PLATFORM_ROLES[index] = {
    ...MOCK_PLATFORM_ROLES[index],
    permissions,
  }
}

export async function deleteMockRole(roleId: string): Promise<void> {
  const { MOCK_PLATFORM_ROLES } = await import('@/infrastructure/mock/iam-mock')
  const index = MOCK_PLATFORM_ROLES.findIndex((role) => role.id === roleId)
  if (index === -1) throw new Error(`角色不存在：${roleId}`)
  if (MOCK_PLATFORM_ROLES[index].isSystem) {
    throw new Error('系统内置角色不可删除')
  }
  if (MOCK_PLATFORM_ROLES[index].userCount > 0) {
    throw new Error('该角色仍有用户归属，请先转移用户')
  }
  MOCK_PLATFORM_ROLES.splice(index, 1)
}

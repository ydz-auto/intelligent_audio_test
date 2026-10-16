/**
 * 用户管理 API 桩（infrastructure 层，红线④：mock 常量）。
 * 契约对照 user_bp.py 实测（INT-30 已落，INT-347 §2.0）：
 * GET /users（分页 ≤100 + status/keyword/role_id 过滤）、POST /users、
 * PUT /users/{id}、POST /users/{id}/role、POST+DELETE /users/{id}/permissions、
 * DELETE /users/{id}；权限门槛 user:read/create/update/assign_role/grant_permission/delete。
 * TODO(API 接线): fetch 换真实 client；mock 写操作仅本地数组变更。
 */
import type { PlatformUser, PlatformUserStatus } from '@/domain/models/user'
import { MOCK_PLATFORM_USERS } from '@/infrastructure/mock/iam-mock'

export const USERS_QUERY_KEY = ['iam', 'users'] as const

export type UserListFilter = {
  keyword?: string
  status?: PlatformUserStatus | 'all'
  /** 多选角色码（FacetedFilter 多选口径，INT-347 §4.4.1） */
  roleCodes?: string[]
}

export async function getUsers(filter: UserListFilter = {}): Promise<PlatformUser[]> {
  return MOCK_PLATFORM_USERS.filter((user) => {
    if (filter.status && filter.status !== 'all' && user.status !== filter.status) {
      return false
    }
    if (
      filter.roleCodes &&
      filter.roleCodes.length > 0 &&
      !filter.roleCodes.includes(user.roleCode)
    ) {
      return false
    }
    if (filter.keyword) {
      const kw = filter.keyword.toLowerCase()
      if (
        !user.username.toLowerCase().includes(kw) &&
        !user.email.toLowerCase().includes(kw)
      ) {
        return false
      }
    }
    return true
  })
}

export async function createMockUser(input: {
  username: string
  displayName?: string
  email: string
  password: string
  roleCode: string
  status: PlatformUserStatus
}): Promise<PlatformUser> {
  const user: PlatformUser = {
    id: `mock-${Date.now()}`,
    username: input.username,
    displayName: input.displayName || input.username,
    email: input.email,
    roleCode: input.roleCode,
    roleName: input.roleCode,
    status: input.status,
    extraPermissions: [],
    createdAt: new Date().toISOString(),
  }
  MOCK_PLATFORM_USERS.unshift(user)
  return user
}

export async function updateMockUser(
  userId: string,
  patch: Partial<Pick<PlatformUser, 'displayName' | 'email' | 'status' | 'roleCode' | 'roleName'>>
): Promise<PlatformUser> {
  const index = MOCK_PLATFORM_USERS.findIndex((user) => user.id === userId)
  if (index === -1) throw new Error(`用户不存在：${userId}`)
  MOCK_PLATFORM_USERS[index] = { ...MOCK_PLATFORM_USERS[index], ...patch }
  return MOCK_PLATFORM_USERS[index]
}

export async function deleteMockUser(userId: string): Promise<void> {
  const index = MOCK_PLATFORM_USERS.findIndex((user) => user.id === userId)
  if (index !== -1) MOCK_PLATFORM_USERS.splice(index, 1)
}

export async function assignMockRole(
  userId: string,
  roleCode: string,
  roleName: string
): Promise<void> {
  await updateMockUser(userId, { roleCode, roleName })
}

export async function grantMockPermissions(
  userId: string,
  permissions: string[]
): Promise<void> {
  const index = MOCK_PLATFORM_USERS.findIndex((user) => user.id === userId)
  if (index !== -1) {
    MOCK_PLATFORM_USERS[index] = {
      ...MOCK_PLATFORM_USERS[index],
      extraPermissions: permissions,
    }
  }
}

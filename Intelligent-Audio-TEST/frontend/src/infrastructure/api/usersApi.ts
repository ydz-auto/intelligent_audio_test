/**
 * 用户管理 API（admin 独占）—— /api/v1/auth/users 全链
 * 权限码：user:read / user:create / user:update / user:delete /
 *         user:assign_role / user:grant_permission
 */
import { request } from '../http/client'
import type { SystemUser, SystemUserPage } from '../../domain/model/system'
import { toSystemUserPage, toSystemUser } from '../adapters/systemAdapter'
import type { UserListDto, UserDetailDto } from '../dto/systemDto'

export interface UserQuery {
  page?: number
  page_size?: number
  status?: string
  keyword?: string
  role_id?: number
}

export interface UserCreateInput {
  username: string
  email?: string
  password?: string
  role_id?: number
}

export interface UserUpdateInput {
  username?: string
  email?: string
  status?: string
  password?: string
}

export const usersApi = {
  /** 用户列表（分页 ≤100） */
  async getAll(params: UserQuery = {}) {
    const dto = await request<UserListDto>('GET', '/auth/users', null, { params });
    return toSystemUserPage(dto);
  },

  /** 用户详情（含 role_name / 生效权限 / overrides 明细） */
  async getDetail(userId: number): Promise<SystemUser> {
    const dto = await request<UserDetailDto>('GET', `/auth/users/${userId}`);
    return toSystemUser(dto);
  },

  /** 新建用户（admin 任意 AUTH_MODE） */
  async create(input: UserCreateInput) {
    return request<{ user_id: number }>('POST', '/auth/users', {
      username: input.username,
      email: input.email,
      password: input.password,
      role_id: input.role_id,
    });
  },

  /** 更新用户资料（缺省键不修改） */
  async update(userId: number, input: UserUpdateInput) {
    return request('PUT', `/auth/users/${userId}`, {
      username: input.username,
      email: input.email,
      status: input.status,
      password: input.password,
    });
  },

  /** 软删除用户（不可删自己） */
  async remove(userId: number) {
    return request('DELETE', `/auth/users/${userId}`);
  },

  /** 分配用户角色（不可改自己角色） */
  async assignRole(userId: number, roleId: number) {
    return request('POST', `/auth/users/${userId}/role`, { role_id: roleId });
  },

  /** 授予用户附加权限码（'*' 拒绝） */
  async grantPermission(userId: number, permission: string) {
    return request('POST', `/auth/users/${userId}/permissions`, { permission });
  },

  /** 差量撤销用户权限 */
  async revokePermission(userId: number, permissionId: number) {
    return request('DELETE', `/auth/users/${userId}/permissions/${permissionId}`);
  },
}

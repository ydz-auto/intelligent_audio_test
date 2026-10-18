/**
 * 角色权限管理 API（admin 独占）—— /api/v1/auth/roles 全链
 * 权限码：role:read / role:create / role:update / role:delete / permission:read
 */
import { request } from '../http/client'
import type { SystemRoleList, PermissionList } from '../../domain/model/system'
import { toSystemRoleList, toPermissionList } from '../adapters/systemAdapter'
import type {
  RoleListDto,
  RoleDetailDto,
  PermissionListDto,
} from '../dto/systemDto'

export interface RoleCreateInput {
  name: string
  description?: string
  permission_codes?: string[]
}

export interface RoleUpdateInput {
  name?: string
  description?: string
}

export const rolesApi = {
  /** 角色列表 */
  async getAll(): Promise<SystemRoleList> {
    const dto = await request<RoleListDto>('GET', '/auth/roles');
    return toSystemRoleList(dto);
  },

  /** 角色详情（含权限码） */
  async getDetail(roleId: number) {
    const dto = await request<RoleDetailDto>('GET', `/auth/roles/${roleId}`);
    return toSystemRoleList({ roles: [dto] }).roles[0];
  },

  /** 权限点目录（只读） */
  async getPermissions(): Promise<PermissionList> {
    const dto = await request<PermissionListDto>('GET', '/auth/permissions');
    return toPermissionList(dto);
  },

  /** 新建角色 */
  async create(input: RoleCreateInput) {
    return request<{ role_id: number }>('POST', '/auth/roles', {
      name: input.name,
      description: input.description,
      permission_codes: input.permission_codes,
    });
  },

  /** 更新角色（空串=不修改） */
  async update(roleId: number, input: RoleUpdateInput) {
    return request('PUT', `/auth/roles/${roleId}`, {
      name: input.name,
      description: input.description,
    });
  },

  /** 删除角色（系统内置 400 / 被引用 409） */
  async remove(roleId: number) {
    return request('DELETE', `/auth/roles/${roleId}`);
  },

  /** 全量替换角色权限（admin '*' 不可移除） */
  async assignPermissions(roleId: number, permissionCodes: string[]) {
    return request('POST', `/auth/roles/${roleId}/permissions`, {
      permission_codes: permissionCodes,
    });
  },
}

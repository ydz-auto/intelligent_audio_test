/**
 * 系统设置域 DTO —— snake_case，与后端 schema 一一对应
 * 仅 adapters/ 和 api/ 允许 import。
 */
import type { PaginatedDto } from './common'

/** 用户列表条目（auth 服务回传；字段可缺失，adapter 兜底） */
export interface UserItemDto {
  id: number
  username: string
  email?: string
  /** active / inactive / locked */
  status?: string
  role_id?: number | null
  role_name?: string
  permissions?: string[]
  created_at?: string
}

export type UserListDto = PaginatedDto<UserItemDto>

/** 用户详情（含 role_name / 生效权限 / overrides 明细） */
export interface UserDetailDto {
  id: number
  username: string
  email?: string
  status?: string
  role_id?: number | null
  role_name?: string
  permissions?: string[]
  overrides?: unknown[]
  created_at?: string
}

/** 创建用户请求 */
export interface UserCreateDto {
  username: string
  email?: string
  password?: string
  role_id?: number
}

/** 更新用户请求（键缺省=不修改） */
export interface UserUpdateDto {
  username?: string
  email?: string
  status?: string
  password?: string
}

/** 角色条目 */
export interface RoleItemDto {
  id: number
  name: string
  description?: string
  permissions?: string[]
  is_system?: boolean
  user_count?: number
  created_at?: string
}

/** 角色列表响应 */
export interface RoleListDto {
  roles: RoleItemDto[]
}

/** 角色详情 */
export interface RoleDetailDto extends RoleItemDto {}

/** 权限点条目 */
export interface PermissionItemDto {
  code: string
  description?: string
  module?: string
}

/** 权限列表响应 */
export interface PermissionListDto {
  permissions: PermissionItemDto[]
}

/** 创建角色请求 */
export interface RoleCreateDto {
  name: string
  description?: string
  permission_codes?: string[]
}

/** 更新角色请求 */
export interface RoleUpdateDto {
  name?: string
  description?: string
}

/** 角色权限全量替换请求 */
export interface RolePermissionsDto {
  permission_codes: string[]
}

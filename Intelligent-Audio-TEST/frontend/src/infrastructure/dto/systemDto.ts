/**
 * 系统设置域 DTO —— snake_case，与后端 schema 一一对应
 * 仅 adapters/ 和 api/ 允许 import。
 */
import type { PaginatedDto } from './common'

/** 用户附加权限 override 明细条目（GET /auth/users/{id} 的 overrides 数组元素） */
export interface PermissionOverrideDto {
  permission_id: number
  code: string
  /** true=附加授予；false=基线覆盖撤销 */
  granted: boolean
}

/** 用户列表条目（auth 服务回传；字段可缺失，adapter 兜底） */
export interface UserItemDto {
  id: number
  username: string
  email?: string
  /** active / inactive / locked */
  status?: string
  role_id?: number | null
  role_name?: string
  /** 生效权限（角色基线 ∪ overrides）权限码全集——仅详情查询返回（INT-1465 列表已瘦身） */
  permissions?: string[]
  /** 生效权限数（列表专用，INT-1465 列表瘦身后替代 permissions 全集；详情不返回） */
  permission_count?: number
  /** 附加权限 override 明细（仅详情查询返回；列表不含） */
  overrides?: PermissionOverrideDto[]
  created_at?: string
}

export type UserListDto = PaginatedDto<UserItemDto>

/** 用户详情（含 role_name / 生效权限 / overrides 明细） */
export interface UserDetailDto extends UserItemDto {}

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

/**
 * 权限点条目（GET /auth/permissions）。
 * 后端实际返回 {id, name, description}——name 即权限码（seed_rbac.py 语义，
 * 与 React iam-adapter `code: dto.name` 对齐）；无 code/module 字段。
 */
export interface PermissionItemDto {
  id: number
  /** 权限码（如 task:read / role:read） */
  name: string
  description?: string
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

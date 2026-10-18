/**
 * 角色权限管理端口 —— rolesApi 的直通薄封装（camelCase Domain 契约）。
 * 系统设置「用户与权限 → 角色权限管理」页面 import 此处。
 */
import { rolesApi } from '../../infrastructure/api'

export const rolesPort = rolesApi

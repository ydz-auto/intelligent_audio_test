/**
 * 用户管理端口 —— usersApi 的直通薄封装（camelCase Domain 契约）。
 * 系统设置「用户与权限 → 用户管理」页面 import 此处。
 */
import { usersApi } from '../../infrastructure/api'

export const usersPort = usersApi

/**
 * 系统选项 KV 端口 —— optionsApi 的直通薄封装（camelCase Domain 契约，
 * snake_case 转换收敛在 infrastructure 层）。
 * 系统设置各域页面一律 import { optionsPort } from此处。
 */
import { optionsApi } from '../../infrastructure/api'

export const optionsPort = optionsApi

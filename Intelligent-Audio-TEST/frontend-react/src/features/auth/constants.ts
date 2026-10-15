import { z } from 'zod'

import {
  AUTH_ERROR_COPY,
  ENCRYPTION_INIT_FAILED_COPY,
  NETWORK_FAILED_COPY,
} from '@/domain/models/auth'

/**
 * 登录/注册表单校验与文案（红线④：mock 常量；文案对齐
 * doc/UX设计规范/12_登录与错误页.md §3.3/§3.6/§7）。
 */

export const loginFormSchema = z.object({
  username: z.string().min(1, '请输入用户名或邮箱'),
  password: z.string().min(1, '请输入密码'),
})

export type LoginForm = z.infer<typeof loginFormSchema>

/** 注册表单（§3.6：四字段 + 确认密码 refine；密码下限 AUTH_PASSWORD_MIN_LENGTH=6 实测） */
export const registerFormSchema = z
  .object({
    username: z.string().min(1, '请输入用户名'),
    email: z.string().min(1, '请输入邮箱').email('请输入有效的邮箱地址'),
    password: z.string().min(6, '请输入密码（至少 6 位）'),
    confirmPassword: z.string().min(1, '请再次输入密码'),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: '两次输入的密码不一致',
    path: ['confirmPassword'],
  })

export type RegisterForm = z.infer<typeof registerFormSchema>

/** 登录页品牌文案 */
export const LOGIN_BRAND_NAME = '智能语音测试平台'
export const LOGIN_BRAND_SLOGAN = '端到端测试 · API 测试 · 多维评估'
/** 演示环境提示（mock 登录口径） */
export const MOCK_LOGIN_HINT = '演示环境：任意账号密码均可登录'
/** 演示触发词说明（105/106 错误码映射可视化用） */
export const MOCK_ERROR_HINT = '演示触发词：error_105 / error_106 / closed'

/** 服务端错误呈现文案（§3.4 三层分离：字段校验内联 / 服务端 toast / 加密失败 Alert） */
export const LOGIN_ERROR_COPY = {
  ...AUTH_ERROR_COPY,
  encryptionInit: ENCRYPTION_INIT_FAILED_COPY,
  network: NETWORK_FAILED_COPY,
} as const

/** OAuth 分隔线文案（newAPI「或继续使用」本地化） */
export const OAUTH_DIVIDER_TEXT = '或使用账号登录'
/** OAuth 处理中文案 */
export const OAUTH_PROCESSING_TEXT = '正在完成登录…'

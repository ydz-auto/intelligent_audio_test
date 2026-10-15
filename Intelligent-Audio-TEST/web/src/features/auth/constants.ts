import { z } from 'zod'

/**
 * 登录表单校验（红线④：演示环境任意账号密码可登录，仅非空校验；
 * 文案对齐 doc/UX设计规范/12_登录与错误页.md §3.3）。
 */

export const loginFormSchema = z.object({
  username: z.string().min(1, '请输入用户名'),
  password: z.string().min(1, '请输入密码'),
})

export type LoginForm = z.infer<typeof loginFormSchema>

/** 登录页品牌文案 */
export const LOGIN_BRAND_NAME = '智能语音测试平台'
export const LOGIN_BRAND_SLOGAN = '端到端测试 · API 测试 · 多维评估'
/** 演示环境提示（mock 登录口径） */
export const MOCK_LOGIN_HINT = '演示环境：任意账号密码均可登录'

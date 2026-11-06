import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'

import { ProfilePage } from '@/features/profile'

/**
 * /profile 个人中心（13_个人中心.md §3.7）：
 * 登录壳 _authenticated 组内页面，无权限码 meta（登录即可，00 总表 §2.1）；
 * 浏览器标题「个人中心」由页面组件设置（§3.1）。
 * validateSearch：bind_ticket/bind_error（OAuth 绑定回调经 /AccountSettings 旧链
 * redirect 保留 query 落此页，页面 onMount 消化后清参，§3.5.2）。
 */
const profileSearchSchema = z.object({
  bind_ticket: z.string().optional(),
  bind_error: z.string().optional(),
})

export const Route = createFileRoute('/_authenticated/profile')({
  validateSearch: profileSearchSchema,
  component: ProfilePage,
})

import { createFileRoute, redirect } from '@tanstack/react-router'

import { authApi } from '@/infrastructure/api/authApi'
import {
  ensureAuthSession,
  useAuthStore,
} from '@/infrastructure/stores/auth-store'
import Home from '@/features/home'

/**
 * / 首页门户（03_首页.md §3.1）：默认公开路由，已登录仍显示门户页。
 * 「首页注册后可见」开启（或邀请码注册开启强制生效）时，未登录访问跳登录页，
 * 登录成功后回跳首页；策略经公开端点 GET /auth/registration-policy 读取。
 */
export const Route = createFileRoute('/')({
  beforeLoad: async () => {
    // 先等会话引导就绪（与 _authenticated 同源），避免把已登录用户误判为未登录
    await ensureAuthSession()
    if (useAuthStore.getState().user) {
      return
    }
    const policy = await authApi.getRegistrationPolicy().catch(() => null)
    if (policy?.homeRequireRegistration) {
      throw redirect({ to: '/login', search: { redirect: '/' } })
    }
  },
  component: Home,
})

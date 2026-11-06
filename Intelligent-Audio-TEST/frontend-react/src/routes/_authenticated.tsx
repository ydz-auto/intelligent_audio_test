import { Outlet, createFileRoute, redirect } from '@tanstack/react-router'

import { AuthenticatedLayout } from '@/components/layout/components/authenticated-layout'
import {
  ensureAuthSession,
  useAuthStore,
} from '@/infrastructure/stores/auth-store'

/**
 * 认证守卫（12_登录与错误页.md §3.1）：
 * 未登录 → /login（携带 sanitize 前置的回跳地址）；已登录渲染工作台布局壳。
 * AUTH_MODE=off 开放模式：无 token 以 dev_user 放行（Vue AuthMode.OFF 口径，
 * §3.1）；beforeLoad 先 await 会话引导，保证直接进 /dashboard 或点「进入
 * 工作台」首次导航即已就绪（不依赖挂载 effect 时序）。
 */
export const Route = createFileRoute('/_authenticated')({
  beforeLoad: async ({ location }) => {
    await ensureAuthSession()
    if (!useAuthStore.getState().user) {
      throw redirect({
        to: '/login',
        search: { redirect: location.href },
      })
    }
  },
  component: () => (
    <AuthenticatedLayout>
      <Outlet />
    </AuthenticatedLayout>
  ),
})

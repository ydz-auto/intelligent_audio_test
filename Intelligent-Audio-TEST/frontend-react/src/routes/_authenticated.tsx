import { Outlet, createFileRoute, redirect } from '@tanstack/react-router'

import { AuthenticatedLayout } from '@/components/layout/components/authenticated-layout'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/**
 * 认证守卫（12_登录与错误页.md §3.1）：
 * 未登录 → /login（携带 sanitize 前置的回跳地址）；已登录渲染控制台布局壳。
 * mock 会话取自 zustand persist（红线④）。
 */
export const Route = createFileRoute('/_authenticated')({
  beforeLoad: ({ location }) => {
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

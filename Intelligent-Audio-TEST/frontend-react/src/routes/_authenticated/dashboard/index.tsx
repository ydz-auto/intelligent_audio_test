import { createFileRoute, redirect } from '@tanstack/react-router'

import { hasPermission } from '@/domain/models/user'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { DashboardPage } from '@/features/dashboard'

/**
 * /dashboard 工作台（home:read 守卫；04_控制台.md §3.3——无子路由单页）。
 * 页面本体（引导卡/概览卡/最近任务/任务统计图表）随 INT-378 卡落位（mock 可视稿）。
 */
export const Route = createFileRoute('/_authenticated/dashboard/')({
  beforeLoad: () => {
    const user = useAuthStore.getState().user
    if (!hasPermission(user, 'home:read')) {
      throw redirect({ to: '/403' })
    }
  },
  component: DashboardPage,
})

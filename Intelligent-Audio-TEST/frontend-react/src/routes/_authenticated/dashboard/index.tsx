import { createFileRoute } from '@tanstack/react-router'

import { requirePermission } from '@/application/auth/route-guards'
import { DashboardPage } from '@/features/dashboard'

/**
 * /dashboard 工作台（home:read 守卫；04_控制台.md §3.3——无子路由单页）。
 * 页面本体（引导卡/概览卡/最近任务/任务统计图表）随 INT-378 卡落位（mock 可视稿）。
 */
export const Route = createFileRoute('/_authenticated/dashboard/')({
  beforeLoad: ({ location }) => {
    requirePermission('home:read', location)
  },
  component: DashboardPage,
})

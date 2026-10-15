import { createFileRoute, redirect } from '@tanstack/react-router'
import { z } from 'zod'

import { hasPermission } from '@/domain/models/user'
import { ReportCenterPage } from '@/features/reports'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/**
 * 报告中心 /reports（INT-434 落位；旧链 /test-reports、/history-reports redirect 见同层路由）。
 * beforeLoad：report:read 守卫 → 无码整页 /403（顶部导航「报告」+ 侧栏「报告中心」同码隐藏）。
 * validateSearch：URL 态全量（tab/page/pageSize/search/type/status/timeRange/startTime/endTime/
 * algorithmType/favorite/trash/sortBy/sortOrder），zod .catch 兜底，URL 可分享（规范 §3.2）。
 */
export const reportsSearchSchema = z
  .object({
    tab: z.enum(['test', 'history']).catch('history'),
    view: z.enum(['table', 'card']).catch('table'),
    page: z.coerce.number().int().min(1).catch(1),
    pageSize: z.coerce.number().int().min(1).catch(20),
    search: z.string().optional().catch(undefined),
    type: z
      .enum(['task', 'comparison', 'secondary_comparison'])
      .optional()
      .catch(undefined),
    status: z.enum(['draft', 'published']).optional().catch(undefined),
    timeRange: z
      .enum(['today', 'yesterday', 'week', 'month', 'custom'])
      .optional()
      .catch(undefined),
    startTime: z.string().optional().catch(undefined),
    endTime: z.string().optional().catch(undefined),
    algorithmType: z.string().optional().catch(undefined),
    favorite: z
      .enum(['true', 'false'])
      .optional()
      .transform((v) => v === 'true')
      .catch(false),
    trash: z
      .enum(['true', 'false'])
      .optional()
      .transform((v) => v === 'true')
      .catch(false),
    sortBy: z.enum(['created_at', 'name', 'pass_rate', 'total_cases']).catch('created_at'),
    sortOrder: z.enum(['asc', 'desc']).catch('desc'),
  })
  .partial()
  .catch({})

export type { ReportsSearch } from '@/features/reports/types'

export const Route = createFileRoute('/_authenticated/reports')({
  validateSearch: reportsSearchSchema,
  beforeLoad: () => {
    const user = useAuthStore.getState().user
    if (!hasPermission(user, 'report:read')) {
      throw redirect({ to: '/403' })
    }
  },
  component: ReportCenterPage,
})

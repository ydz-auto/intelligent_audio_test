import { createFileRoute, redirect } from '@tanstack/react-router'
import { z } from 'zod'

import { hasPermission } from '@/domain/models/user'
import { ReportShowcasePage } from '@/features/reports-showcase'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/**
 * 报告展示页 /reports（INT-434 重实施 / INT-441 双入口拆分；15_报告域.md §2.1）。
 * 顶部导航「报告」直达，对外展示已发布报告、弱管理；管理操作集中在 /report-center。
 * beforeLoad：report:read 守卫 → 无码整页 /403（顶部导航「报告」同码隐藏）。
 * validateSearch：URL 态（view/page/pageSize/search/type/timeRange/startTime/endTime/
 * algorithmType/sortBy/sortOrder），zod .catch 兜底，URL 可分享。
 */
export const reportsShowcaseSearchSchema = z
  .object({
    view: z.enum(['table', 'card']).catch('table'),
    page: z.coerce.number().int().min(1).catch(1),
    pageSize: z.coerce.number().int().min(1).catch(20),
    search: z.string().optional().catch(undefined),
    type: z
      .enum(['task', 'comparison', 'secondary_comparison', 'benchmark'])
      .optional()
      .catch(undefined),
    timeRange: z
      .enum(['today', 'yesterday', 'week', 'month', 'custom'])
      .optional()
      .catch(undefined),
    startTime: z.string().optional().catch(undefined),
    endTime: z.string().optional().catch(undefined),
    algorithmType: z.string().optional().catch(undefined),
    sortBy: z.enum(['created_at', 'name', 'pass_rate', 'total_cases']).catch('created_at'),
    sortOrder: z.enum(['asc', 'desc']).catch('desc'),
  })
  .partial()
  .catch({})

export type { ShowcaseSearch } from '@/features/reports-showcase/types'

export const Route = createFileRoute('/_authenticated/reports')({
  validateSearch: reportsShowcaseSearchSchema,
  beforeLoad: () => {
    const user = useAuthStore.getState().user
    if (!hasPermission(user, 'report:read')) {
      throw redirect({ to: '/403' })
    }
  },
  component: ReportShowcasePage,
})

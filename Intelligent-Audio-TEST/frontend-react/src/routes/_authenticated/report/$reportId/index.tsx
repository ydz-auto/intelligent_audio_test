import { createFileRoute, redirect } from '@tanstack/react-router'
import { z } from 'zod'

import { requirePermission } from '@/application/auth/route-guards'
import { ReportViewPage } from '@/features/report-view'

/**
 * 报告查看 /report/$reportId（INT-434 重实施；15_报告域.md §3 真实层级）。
 * beforeLoad：report:read 守卫 → 无码 /403?from；参数非数字回退报告中心。
 * search：from=showcase|management 标记来源入口（返回按钮回退来源；§3.1）。
 */
export const Route = createFileRoute('/_authenticated/report/$reportId/')({
  validateSearch: z
    .object({ from: z.enum(['showcase', 'management']).optional().catch(undefined) })
    .partial()
    .catch({}),
  beforeLoad: ({ params, location }) => {
    requirePermission('report:read', location)
    const reportId = Number(params.reportId)
    if (!Number.isFinite(reportId) || reportId <= 0) {
      throw redirect({ to: '/report-center' })
    }
  },
  component: ReportViewPage,
})

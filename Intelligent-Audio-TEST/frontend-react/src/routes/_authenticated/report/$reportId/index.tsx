import { createFileRoute, redirect } from '@tanstack/react-router'

import { hasPermission } from '@/domain/models/user'
import { ReportViewPage } from '@/features/report-view'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/**
 * 报告查看 /report/$reportId（INT-434 落位；阅读优先版式，规范 §4）。
 * beforeLoad：report:read 守卫 → 无码 /403；参数非数字回退报告中心。
 */
export const Route = createFileRoute('/_authenticated/report/$reportId/')({
  beforeLoad: ({ params }) => {
    const user = useAuthStore.getState().user
    if (!hasPermission(user, 'report:read')) {
      throw redirect({ to: '/403' })
    }
    const reportId = Number(params.reportId)
    if (!Number.isFinite(reportId) || reportId <= 0) {
      throw redirect({ to: '/reports' })
    }
  },
  component: ReportViewPage,
})

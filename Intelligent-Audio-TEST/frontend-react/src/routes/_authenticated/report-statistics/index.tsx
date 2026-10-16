import { createFileRoute, redirect } from '@tanstack/react-router'

import { hasPermission } from '@/domain/models/user'
import { ReportStatisticsPage } from '@/features/report-statistics'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/**
 * 报告统计分析页 /report-statistics（15_报告域.md §2.2，INT-500 路由定稿；00 页面清单 §2.1 登记）。
 * 入口=报告中心工具栏「更多操作 ⋯ → 统计分析」；report:read 守卫 → 无码整页 /403。
 * 四标签页（统计维度/统计结果/趋势分析/报表生成）+ 维度统计 + 统计结果导出。
 */
export const Route = createFileRoute('/_authenticated/report-statistics/')({
  beforeLoad: () => {
    const user = useAuthStore.getState().user
    if (!hasPermission(user, 'report:read')) {
      throw redirect({ to: '/403' })
    }
  },
  component: ReportStatisticsPage,
})

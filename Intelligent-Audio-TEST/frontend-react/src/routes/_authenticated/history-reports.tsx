import { createFileRoute, redirect } from '@tanstack/react-router'

/**
 * 旧链 /history-reports → /report-center?tab=history（15_报告域.md §2：历史报告并入
 * 报告中心管理页双页签，redirect 兼容；INT-441 双入口拆分后管理页迁至 /report-center）。
 */
export const Route = createFileRoute('/_authenticated/history-reports')({
  beforeLoad: () => {
    throw redirect({ to: '/report-center', search: { tab: 'history' } })
  },
})

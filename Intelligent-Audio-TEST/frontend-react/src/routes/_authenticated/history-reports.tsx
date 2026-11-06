import { createFileRoute, redirect } from '@tanstack/react-router'

/**
 * 旧链 /history-reports → /report-center（15_报告域.md §2：历史报告并入
 * 报告中心管理页；口径修正 2026-10-16：报告类型为筛选属性，redirect 不再带 tab 语义）。
 */
export const Route = createFileRoute('/_authenticated/history-reports')({
  beforeLoad: () => {
    throw redirect({ to: '/report-center' })
  },
})

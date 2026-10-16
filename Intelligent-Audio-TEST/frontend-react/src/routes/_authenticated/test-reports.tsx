import { createFileRoute, redirect } from '@tanstack/react-router'

/**
 * 旧链 /test-reports → /report-center?tab=test（15_报告域.md §2：测试报告并入报告中心
 * 管理页双页签，redirect 兼容；INT-441 双入口拆分后管理页迁至 /report-center）。
 */
export const Route = createFileRoute('/_authenticated/test-reports')({
  beforeLoad: () => {
    throw redirect({ to: '/report-center', search: { tab: 'test' } })
  },
})

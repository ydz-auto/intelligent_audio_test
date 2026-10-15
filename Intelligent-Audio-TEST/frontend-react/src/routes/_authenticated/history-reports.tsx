import { createFileRoute, redirect } from '@tanstack/react-router'

/**
 * 旧链 /history-reports → /reports?tab=history（规范 §3.2：历史报告并入报告中心双页签，redirect 兼容）。
 */
export const Route = createFileRoute('/_authenticated/history-reports')({
  beforeLoad: () => {
    throw redirect({ to: '/reports', search: { tab: 'history' } })
  },
})

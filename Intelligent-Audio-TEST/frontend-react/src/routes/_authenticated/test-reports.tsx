import { createFileRoute, redirect } from '@tanstack/react-router'

/**
 * 旧链 /test-reports → /reports?tab=test（规范 §3.2：测试报告并入报告中心双页签，redirect 兼容）。
 */
export const Route = createFileRoute('/_authenticated/test-reports')({
  beforeLoad: () => {
    throw redirect({ to: '/reports', search: { tab: 'test' } })
  },
})

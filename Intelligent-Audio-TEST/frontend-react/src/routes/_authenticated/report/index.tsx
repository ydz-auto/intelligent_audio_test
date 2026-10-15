import { createFileRoute, redirect } from '@tanstack/react-router'

/**
 * 旧 query 入口 /report?id=xxx → /report/$reportId（规范 §2.1 redirect 兼容）。
 * 无 id 或非法 id 回退报告中心。
 */
export const Route = createFileRoute('/_authenticated/report/')({
  beforeLoad: ({ location }) => {
    const raw = new URLSearchParams(location.searchStr).get('id')
    const reportId = Number(raw)
    if (!raw || !Number.isFinite(reportId) || reportId <= 0) {
      throw redirect({ to: '/reports' })
    }
    throw redirect({ to: '/report/$reportId', params: { reportId: String(reportId) } })
  },
})

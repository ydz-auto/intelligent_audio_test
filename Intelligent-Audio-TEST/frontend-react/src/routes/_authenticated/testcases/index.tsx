import { createFileRoute, redirect } from '@tanstack/react-router'

/**
 * /testcases → /testcases/by-group（11_用例域.md §3.2：index 重定向默认视图）。
 */
export const Route = createFileRoute('/_authenticated/testcases/')({
  beforeLoad: () => {
    throw redirect({
      to: '/testcases/$view',
      params: { view: 'by-group' },
    })
  },
})

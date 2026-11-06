import { createFileRoute, redirect } from '@tanstack/react-router'

/**
 * /tasks → /tasks/daily（09_任务域.md §3.2：index 重定向默认页签）。
 */
export const Route = createFileRoute('/_authenticated/tasks/')(
  {
    beforeLoad: () => {
      throw redirect({ to: '/tasks/$tab', params: { tab: 'daily' } })
    },
  }
)

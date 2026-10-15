import { createFileRoute } from '@tanstack/react-router'

import { NotFoundError } from '@/features/errors/not-found-error'

/** /404 错误页（同时作为根路由 notFoundComponent，12_登录与错误页.md §4） */
export const Route = createFileRoute('/_errors/404')({
  component: () => <NotFoundError />,
})

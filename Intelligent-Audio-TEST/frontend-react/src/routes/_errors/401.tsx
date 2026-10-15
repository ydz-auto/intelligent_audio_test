import { createFileRoute } from '@tanstack/react-router'

import { UnauthorizedError } from '@/features/errors/unauthorized-error'

/** /401 错误页（五页全建，12_登录与错误页.md §4） */
export const Route = createFileRoute('/_errors/401')({
  component: () => <UnauthorizedError />,
})

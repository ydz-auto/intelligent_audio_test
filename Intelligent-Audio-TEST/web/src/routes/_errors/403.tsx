import { createFileRoute } from '@tanstack/react-router'

import { ForbiddenError } from '@/features/errors/forbidden'

/** /403 错误页（路由守卫无权限时统一落此页，12_登录与错误页.md §4） */
export const Route = createFileRoute('/_errors/403')({
  component: () => <ForbiddenError />,
})

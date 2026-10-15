import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'

import { ForbiddenError } from '@/features/errors/forbidden'

const forbiddenSearchSchema = z.object({
  /** 守卫 redirect 携带的来源路径（§4.3：说明行下 muted 小字） */
  from: z.string().optional(),
})

/** /403 错误页（路由守卫无权限时统一落此页，12_登录与错误页.md §4.3） */
export const Route = createFileRoute('/_errors/403')({
  validateSearch: forbiddenSearchSchema,
  component: ForbiddenPage,
})

function ForbiddenPage() {
  const { from } = Route.useSearch()
  return <ForbiddenError from={from} />
}

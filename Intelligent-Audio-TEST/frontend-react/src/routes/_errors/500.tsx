import { createFileRoute } from '@tanstack/react-router'

import { GeneralError } from '@/features/errors/general-error'

/** /500 错误页（同时作为根路由 errorComponent，12_登录与错误页.md §4） */
export const Route = createFileRoute('/_errors/500')({
  component: () => <GeneralError />,
})

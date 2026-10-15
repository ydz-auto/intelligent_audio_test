import { createFileRoute } from '@tanstack/react-router'

import { PagePlaceholder } from '@/features/placeholder/page-placeholder'

/** 任务管理（四页签列表，归 INT-354 卡） */
export const Route = createFileRoute('/_authenticated/tasks')({
  component: () => (
    <PagePlaceholder title='任务管理' note='四页签列表随 INT-354 卡落地' />
  ),
})

import { createFileRoute } from '@tanstack/react-router'

import { PagePlaceholder } from '@/features/placeholder/page-placeholder'

/** 用例管理（双视图表格，归 INT-356 卡） */
export const Route = createFileRoute('/_authenticated/testcases')({
  component: () => (
    <PagePlaceholder title='用例管理' note='双视图表格随 INT-356 卡落地' />
  ),
})

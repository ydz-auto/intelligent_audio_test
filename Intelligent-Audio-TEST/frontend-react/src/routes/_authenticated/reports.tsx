import { createFileRoute } from '@tanstack/react-router'

import { PagePlaceholder } from '@/features/placeholder/page-placeholder'

/** 报告中心（test-reports/history-reports 并入口，归 INT-360 卡） */
export const Route = createFileRoute('/_authenticated/reports')({
  component: () => (
    <PagePlaceholder title='报告中心' note='报告域随 INT-360 卡落地' />
  ),
})

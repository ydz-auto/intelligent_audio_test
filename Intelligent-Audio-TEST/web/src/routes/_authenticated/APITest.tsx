import { createFileRoute } from '@tanstack/react-router'

import { PagePlaceholder } from '@/features/placeholder/page-placeholder'

/** API 测试（页面规范归 INT-355 卡） */
export const Route = createFileRoute('/_authenticated/APITest')({
  component: () => (
    <PagePlaceholder title='API 测试' note='页面随 INT-355 卡落地' />
  ),
})

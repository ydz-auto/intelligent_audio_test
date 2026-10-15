import { createFileRoute } from '@tanstack/react-router'

import { PagePlaceholder } from '@/features/placeholder/page-placeholder'

/** 端到端测试（五步测试流程，页面规范归 INT-355 卡） */
export const Route = createFileRoute('/_authenticated/E2ETest')({
  component: () => (
    <PagePlaceholder
      title='端到端测试'
      note='五步测试流程页面随 INT-355 卡落地'
    />
  ),
})

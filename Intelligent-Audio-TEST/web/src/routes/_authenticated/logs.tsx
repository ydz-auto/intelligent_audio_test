import { createFileRoute } from '@tanstack/react-router'

import { PagePlaceholder } from '@/features/placeholder/page-placeholder'

/** 日志查看（页面规范归配置运维 INT-362 卡） */
export const Route = createFileRoute('/_authenticated/logs')({
  component: () => (
    <PagePlaceholder title='日志查看' note='页面随 INT-362 卡落地' />
  ),
})

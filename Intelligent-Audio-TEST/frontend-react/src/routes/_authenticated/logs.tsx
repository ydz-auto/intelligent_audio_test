import { createFileRoute } from '@tanstack/react-router'

import { requirePermission } from '@/application/auth/route-guards'
import { PagePlaceholder } from '@/features/placeholder/page-placeholder'

/** 日志查看（页面规范归配置运维 INT-362 卡；壳 INT-607 补 log:read 守卫 → 无码 /403?from） */
export const Route = createFileRoute('/_authenticated/logs')({
  beforeLoad: ({ location }) => {
    requirePermission('log:read', location)
  },
  component: () => (
    <PagePlaceholder title='日志查看' note='页面随 INT-362 卡落地' />
  ),
})

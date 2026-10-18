import { createFileRoute } from '@tanstack/react-router'

import { requirePermission } from '@/application/auth/route-guards'
import { LogsPage } from '@/features/logs'

/** 日志查看（/logs，17_配置运维.md §4；INT-693 接线：mock→真实接口）。
 * 壳守卫 requirePermission('log:read') → 无码 /403?from（INT-607 补）。 */
export const Route = createFileRoute('/_authenticated/logs')({
  beforeLoad: ({ location }) => {
    requirePermission('log:read', location)
  },
  component: LogsPage,
})

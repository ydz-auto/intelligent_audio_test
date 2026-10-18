import { createFileRoute } from '@tanstack/react-router'

import { requirePermission } from '@/application/auth/route-guards'
import { LogsPage } from '@/features/logs'

/**
 * 日志查看 /logs（17_配置运维.md §4；INT-763 整页落地，替换 INT-362 占位）。
 * 挂「管理」组（sidebar-nav.config 已注册，图标 FileText）；log:read 守卫 → 无码整页 /403。
 * 整页：SectionPageLayout + 筛选工具条 + 统计徽章 + DataTable + 实时监控 + 导出/清除 Dialog。
 */
export const Route = createFileRoute('/_authenticated/logs')({
  beforeLoad: ({ location }) => {
    requirePermission('log:read', location.pathname)
  },
  component: LogsPage,
})

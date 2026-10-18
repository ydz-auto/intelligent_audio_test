import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'

import { requirePermission } from '@/application/auth/route-guards'
import { ReportCenterPage } from '@/features/reports'

/**
 * 报告中心（管理页） /report-center（INT-434 重实施 / INT-441 双入口拆分落位）。
 * 由工作台侧栏「测试资产」组「报告中心」进入；生成/编辑/发布/删除/批量/导出/收藏/回收站等
 * 管理操作集中本页（15_报告域.md §2）。
 * 口径修正 2026-10-16：取消「测试报告/历史报告」双页签——单一列表视图默认展示全部报告，
 * 报告类型进筛选条件；旧链 /test-reports、/history-reports redirect 见同层路由（不带 tab 语义）。
 * beforeLoad：report:read 守卫 → 无码整页 /403。
 * validateSearch：URL 态全量（page/pageSize/search/type/status/timeRange/startTime/endTime/
 * algorithmType/favorite/trash/sortBy/sortOrder），zod .catch 兜底，URL 可分享。
 */
export const reportCenterSearchSchema = z
  .object({
    view: z.enum(['table', 'card']).catch('table'),
    page: z.coerce.number().int().min(1).catch(1),
    pageSize: z.coerce.number().int().min(1).catch(20),
    search: z.string().optional().catch(undefined),
    type: z
      .enum(['task', 'comparison', 'secondary_comparison', 'benchmark'])
      .optional()
      .catch(undefined),
    status: z.enum(['draft', 'published']).optional().catch(undefined),
    timeRange: z
      .enum(['today', 'yesterday', 'week', 'month', 'custom'])
      .optional()
      .catch(undefined),
    startTime: z.string().optional().catch(undefined),
    endTime: z.string().optional().catch(undefined),
    /** 高级搜索：任务类型/设备类型/创建者（§2 :186-188） */
    taskType: z.string().optional().catch(undefined),
    deviceType: z.string().optional().catch(undefined),
    creator: z.string().optional().catch(undefined),
    algorithmType: z.string().optional().catch(undefined),
    favorite: z
      .union([z.boolean(), z.enum(['true', 'false'])])
      .optional()
      .transform((v) => v === true || v === 'true')
      .catch(false),
    trash: z
      .union([z.boolean(), z.enum(['true', 'false'])])
      .optional()
      .transform((v) => v === true || v === 'true')
      .catch(false),
    sortBy: z
      .enum(['created_at', 'name', 'status', 'algorithm', 'pass_rate', 'total_cases'])
      .catch('created_at'),
    sortOrder: z.enum(['asc', 'desc']).catch('desc'),
  })
  .partial()
  .catch({})

export type { ReportsSearch } from '@/features/reports/types'

export const Route = createFileRoute('/_authenticated/report-center/')({
  validateSearch: reportCenterSearchSchema,
  beforeLoad: ({ location }) => {
    requirePermission('report:read', location)
  },
  component: ReportCenterPage,
})

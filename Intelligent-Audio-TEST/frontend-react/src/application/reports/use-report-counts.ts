/**
 * 报告计数 query（application 层；GET /reports/tab-counts，短 TTL 缓存）。
 * 口径修正 2026-10-16：取消页签后保留为单一列表筛选 chips/徽章行计数源，不再以 tab 为语义。
 * INT-2339/INT-2350：计数与列表同口径——带当前 keyword / favorite / deleted，三者任一变化
 * 都会切换 queryKey 重取（切换关键字必须让计数缓存失效），页头「共 N」/Hero 汇总/徽章行/
 * 类型 chips/工具栏数字因此同步收缩。status / type 属 Tab 自身维度，不入计数入参。
 * 单计数失败降级 0（服务端已降级），前端静默显示。
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import type { ReportCountsQuery } from '@/infrastructure/api/reports-api'
import { fetchReportCounts } from '@/infrastructure/api/reports-api'

export function useReportCounts(filters: ReportCountsQuery = {}) {
  const keyword = filters.keyword ?? ''
  const favorite = filters.favorite ?? false
  const deleted = filters.deleted ?? false
  return useQuery({
    queryKey: ['reports', 'counts', { keyword, favorite, deleted }],
    queryFn: () => fetchReportCounts({ keyword, favorite, deleted }),
    // 换键期间沿用上一份计数，避免页头/徽章/类型 chips 闪 0（列表同样用 keepPreviousData）
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  })
}

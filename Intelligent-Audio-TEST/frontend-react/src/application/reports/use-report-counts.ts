/**
 * 报告全量分类计数 query（application 层；GET /reports/tab-counts，短 TTL 缓存）。
 * 口径修正 2026-10-16：取消页签后保留为单一列表筛选 chips/徽章行计数源，不再以 tab 为语义。
 * 单计数失败降级 0（服务端已降级），前端静默显示。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchReportCounts } from '@/infrastructure/api/reports-api'

export function useReportCounts() {
  return useQuery({
    queryKey: ['reports', 'counts'],
    queryFn: fetchReportCounts,
    staleTime: 60_000,
  })
}

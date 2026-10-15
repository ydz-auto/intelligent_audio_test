/**
 * 报告 Tab 计数 query（application 层；GET /reports/tab-counts，短 TTL 缓存）。
 * 单 Tab 计数失败降级 0（服务端已降级），前端静默显示。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchReportTabCounts } from '@/infrastructure/api/reports-api'

export function useReportTabCounts() {
  return useQuery({
    queryKey: ['reports', 'tab-counts'],
    queryFn: fetchReportTabCounts,
    staleTime: 60_000,
  })
}

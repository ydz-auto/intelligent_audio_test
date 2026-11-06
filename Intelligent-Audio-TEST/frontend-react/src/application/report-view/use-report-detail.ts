/**
 * 报告查看详情 query（application 层；GET /reports/{id} → ReportDetailData）。
 * 404/非法 id → 页面 ErrorState「报告不存在」；渲染异常 → 错误页（页面层处理）。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchReportDetail } from '@/infrastructure/api/reports-api'

export function useReportDetail(reportId: number) {
  return useQuery({
    queryKey: ['reports', 'detail', reportId],
    queryFn: () => fetchReportDetail(reportId),
    staleTime: 30_000,
  })
}

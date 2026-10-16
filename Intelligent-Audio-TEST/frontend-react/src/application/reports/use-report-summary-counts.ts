/**
 * 报告中心 Hero 类型 chips / 收藏计数（application 层，INT-434 P2-20 收敛）。
 * 页面不直 import mock 常量，统一走 API 桩（fetchReportTypeCounts）→ 后续接线只换桩。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchReportTypeCounts } from '@/infrastructure/api/reports-api'

export function useReportSummaryCounts() {
  return useQuery({
    queryKey: ['reports', 'summary-counts'],
    queryFn: fetchReportTypeCounts,
    staleTime: 60_000,
  })
}

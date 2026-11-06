/**
 * 报告展示页已发布列表 query（application 层，INT-441）。
 * 复用 reports 取数（fetchReportList）+ status='published' 过滤（规范 §2.1：展示页仅已发布）；
 * 全局算法大卡（INT-442）写回同一 store 后列表请求自动附 algorithm_type。
 */
import { useQuery } from '@tanstack/react-query'

import type { ReportListQuery } from '@/domain/models/report'
import { fetchReportList } from '@/infrastructure/api/reports-api'

export function usePublishedReportList(query: ReportListQuery) {
  return useQuery({
    queryKey: ['reports', 'showcase', query],
    queryFn: () => fetchReportList({ ...query, status: 'published' }),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  })
}

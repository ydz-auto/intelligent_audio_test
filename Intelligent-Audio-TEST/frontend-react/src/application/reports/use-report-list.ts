/**
 * 报告列表 query（application 层）：服务端分页语义平移（manualPagination 直用）。
 * queryKey 含全量查询对象 —— 任一筛选/分页/排序变化即重查；页面层负责 useMemo 稳定
 * query 引用（URL 态驱动），避免 queryKey 抖动。
 */
import { useQuery } from '@tanstack/react-query'

import type { ReportListQuery } from '@/domain/models/report'
import { fetchReportList } from '@/infrastructure/api/reports-api'

export function useReportList(query: ReportListQuery) {
  return useQuery({
    queryKey: ['reports', query],
    queryFn: () => fetchReportList(query),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  })
}

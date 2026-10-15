/**
 * 具体用例列表/搜索 query（application 层；POST /reports/{id}/cases/search，
 * ReportSearchCasesRequest 全参：keyword/categories/tags/metrics/sort_by/sort_metric/
 * sort_resource/sort_order/page/per_page）。
 */
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import type { ReportSearchCasesRequest } from '@/domain/models/report'
import { searchReportCases } from '@/infrastructure/api/reports-api'

export function useReportCases(
  reportId: number,
  query: ReportSearchCasesRequest
) {
  const key = useMemo(() => JSON.stringify(query), [query])
  return useQuery({
    queryKey: ['reports', 'detail', reportId, 'cases', key],
    queryFn: () => searchReportCases(reportId, query),
    staleTime: 30_000,
  })
}

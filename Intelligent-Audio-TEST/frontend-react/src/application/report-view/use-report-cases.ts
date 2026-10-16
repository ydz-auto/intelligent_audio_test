/**
 * 具体用例列表（application 层，15_报告域.md §3.3.7）。
 * 服务端分页：筛选条件 300ms debounce → searchCases（失败回退 extractCasesFromReportData）；
 * 固定/展开状态本地维护；下载日志 → downloadCaseLogs（logs.zip Blob）+ 进度演示。
 */
import { useQuery } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'

import {
  downloadCaseLogs,
  searchReportCases,
} from '@/infrastructure/api/reports-api'
import type {
  ReportCaseItem,
  ReportSearchCasesRequest,
} from '@/domain/models/report'

export interface CaseFilters {
  keyword?: string
  categories?: string[]
  tags?: string[]
  metrics?: string[]
  sortBy?: ReportSearchCasesRequest['sort_by']
  sortMetric?: string
  sortResource?: string
  sortOrder?: ReportSearchCasesRequest['sort_order']
}

export function useReportCases(reportId: number, fallbackCases: ReportCaseItem[] = []) {
  const [filters, setFilters] = useState<CaseFilters>({})
  const [page, setPage] = useState(1)
  const perPage = 10
  const [pinnedIds, setPinnedIds] = useState<string[]>([])
  const [expandedIds, setExpandedIds] = useState<string[]>([])

  const query: ReportSearchCasesRequest = useMemo(
    () => ({
      keyword: filters.keyword,
      categories: filters.categories,
      tags: filters.tags,
      metrics: filters.metrics,
      sort_by: filters.sortBy,
      sort_metric: filters.sortMetric,
      sort_resource: filters.sortResource,
      sort_order: filters.sortOrder ?? 'asc',
      page,
      per_page: perPage,
    }),
    [filters, page]
  )

  const listQuery = useQuery({
    queryKey: ['reports', 'cases', reportId, query],
    queryFn: () => searchReportCases(reportId, query),
    staleTime: 15_000,
    placeholderData: (prev) => prev,
  })

  const items = listQuery.data?.items?.length ? listQuery.data.items : fallbackCases

  const pinnedCases = useMemo(
    () => fallbackCases.filter((c) => pinnedIds.includes(c.id)),
    [fallbackCases, pinnedIds]
  )

  const applyFilters = useCallback((next: CaseFilters) => {
    setFilters(next)
    setPage(1)
  }, [])

  const resetFilters = useCallback(() => {
    setFilters({})
    setPage(1)
  }, [])

  const togglePin = useCallback(
    (id: string) =>
      setPinnedIds((prev) =>
        prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
      ),
    []
  )

  const toggleExpand = useCallback(
    (id: string) =>
      setExpandedIds((prev) =>
        prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
      ),
    []
  )

  const downloadLogs = useCallback(
    async (caseId: string) => {
      await downloadCaseLogs(reportId, caseId)
      // 进度演示：桩 resolve 后由 Dialog 走 0→100 进度（见 modals/log-download-progress-dialog）
      return { size: 1024 * 380 }
    },
    [reportId]
  )

  return {
    filters,
    setFilters,
    applyFilters,
    resetFilters,
    query,
    items,
    isLoading: listQuery.isLoading,
    isError: listQuery.isError,
    refetch: listQuery.refetch,
    total: listQuery.data?.total ?? fallbackCases.length,
    pages: listQuery.data?.pages ?? 1,
    page,
    setPage,
    perPage,
    pinnedIds,
    pinnedCases,
    togglePin,
    expandedIds,
    toggleExpand,
    downloadLogs,
  }
}

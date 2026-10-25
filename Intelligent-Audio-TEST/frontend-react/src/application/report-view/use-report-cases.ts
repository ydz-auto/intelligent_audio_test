/**
 * 具体用例列表（application 层，15_报告域.md §3.3.7）。
 * 服务端分页：筛选条件 300ms debounce → searchCases（失败回退 extractCasesFromReportData）；
 * 固定/展开状态本地维护；下载日志 → downloadCaseLogs（logs.zip Blob）+ 进度演示。
 * 排序方式（INT-1049）：UI 新增「按标签」（sortBy='tag'）——分组组织维度，后端无 tag 排序，
 * 请求回退 name 排序，组内客户端聚合（specific-case-grouping.ts）；「按分组」/「按标签」均不改数据请求。
 */
import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  downloadCaseLogs,
  searchReportCases,
  type CaseLogDownloadProgress,
} from '@/infrastructure/api/reports-api'
import type {
  ReportCaseItem,
  ReportSearchCasesRequest,
} from '@/domain/models/report'

import { REPORT_CASE_AGGREGATE_LIMIT } from './use-report-case-views'

export interface CaseFilters {
  keyword?: string
  categories?: string[]
  tags?: string[]
  metrics?: string[]
  sortBy?: ReportSearchCasesRequest['sort_by'] | 'tag'
  sortMetric?: string
  sortResource?: string
  sortOrder?: ReportSearchCasesRequest['sort_order']
}

export function useReportCases(
  reportId: number,
  fallbackCases: ReportCaseItem[] = [],
  /** 导出模式强制全量（§3.1：分页强制全量，showPagination && !isExporting 判定） */
  exporting = false
) {
  const [filters, setFilters] = useState<CaseFilters>({})
  // 300ms 防抖（§3.3.7：筛选条件变化后延迟生效，避免每次按键即触发 search）
  const [debouncedFilters, setDebouncedFilters] = useState<CaseFilters>({})
  const [page, setPage] = useState(1)
  /**
   * 取数粒度（INT-1738 三视图）：`report_cases` 一行 = 用例 × 资源，用例视图要按 `test_case_id`
   * 合并多资源行、设备 / 结果类型视图要全量聚合——服务端分页会把同一用例的两行拆到不同页，
   * 故一律取全量（上限 10000，超出走 §3.3.7 降级提示）。
   */
  const perPage = REPORT_CASE_AGGREGATE_LIMIT
  const [pinnedIds, setPinnedIds] = useState<string[]>([])
  const [expandedIds, setExpandedIds] = useState<string[]>([])

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedFilters(filters), 300)
    return () => clearTimeout(timer)
  }, [filters])

  // 筛选条件生效后回到第一页
  useEffect(() => {
    setPage(1)
  }, [debouncedFilters])

  const query: ReportSearchCasesRequest = useMemo(
    () => ({
      keyword: debouncedFilters.keyword,
      categories: debouncedFilters.categories,
      tags: debouncedFilters.tags,
      metrics: debouncedFilters.metrics,
      // 'tag' 为 UI 分组组织维度（后端无 tag 排序），请求回退 name 排序，组内客户端聚合
      sort_by: debouncedFilters.sortBy === 'tag' ? 'name' : debouncedFilters.sortBy,
      sort_metric: debouncedFilters.sortMetric,
      sort_resource: debouncedFilters.sortResource,
      sort_order: debouncedFilters.sortOrder ?? 'asc',
      page,
      per_page: perPage,
    }),
    [debouncedFilters, page]
  )

  const listQuery = useQuery({
    queryKey: ['reports', 'cases', reportId, query],
    queryFn: () => searchReportCases(reportId, query),
    // 导出态不取缓存（快照全文必须现取），常规态 15s 内复用
    staleTime: exporting ? 0 : 15_000,
    placeholderData: (prev) => prev,
  })

  // P2-5：仅当 data 未返回（加载/占位）时回退 fallbackCases；合法空结果（items=[]）进入空态分支
  const items = listQuery.data ? listQuery.data.items : fallbackCases

  const pinnedCases = useMemo(
    () => fallbackCases.filter((c) => pinnedIds.includes(c.id)),
    [fallbackCases, pinnedIds]
  )

  const applyFilters = useCallback((next: CaseFilters) => {
    // 立即提交（「应用筛选」按钮语义：跳过防抖，马上生效）
    setFilters(next)
    setDebouncedFilters(next)
    setPage(1)
  }, [])

  const resetFilters = useCallback(() => {
    setFilters({})
    setDebouncedFilters({})
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

  /** 切视图清空展开态（§3.3.7：用例卡在视图间的身份与位置都变了） */
  const clearExpanded = useCallback(() => setExpandedIds([]), [])

  /**
   * 下载用例日志（INT-1067 两段流程第二步）：按所选文件名打包（?files=），
   * 流式上报真实进度（onProgress 500ms 采样）；INT-1116 presigned 模式携带 download_url
   * 供浏览器直连 OSS 下载，否则返回 zip Blob。
   */
  const downloadLogs = useCallback(
    async (
      caseId: string,
      files: string[],
      onProgress?: (progress: CaseLogDownloadProgress) => void
    ) => {
      // 消费真实端点返回的 blob / presigned download_url（进度 Dialog 按所选总量与真实速率推进）
      return downloadCaseLogs(reportId, caseId, files, onProgress)
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
    clearExpanded,
    downloadLogs,
  }
}

/**
 * /reports 报告展示页（INT-434 重实施 / INT-441 双入口拆分；15_报告域.md §2.1）。
 * 导航栏「报告」直达：对外展示已发布报告成果，弱管理——行操作仅「查看/复制链接」。
 * 算法切换经「算法卡片网格」（INT-486 口径：每算法一张大卡点击选中，写回全局 store，
 * 本页不渲染右上角联动 chip，INT-442）。URL 态经 validateSearch
 * （features/reports-showcase/types.ts），页面以 navigate 回写。
 */
import { useNavigate, useSearch } from '@tanstack/react-router'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { usePublishedReportList } from '@/application/reports-showcase/use-published-report-list'
import { useGlobalAlgorithm } from '@/application/hooks/use-global-algorithm'
import { toGlobalAlgorithmId, toReportAlgorithmType } from '@/features/reports/lib/algorithm'
import { buildShowcaseQuery } from '@/application/reports/report-query'
import { ReportsPagination } from '@/features/reports/components/reports-pagination'
import type { ShowcaseSearch } from '@/features/reports-showcase/types'

import { AlgorithmCardGrid, ALL_ALGORITHMS_SENTINEL } from '@/components/algorithm-card-grid'
import { ReportShowcaseHero } from './components/report-showcase-hero'
import { ReportShowcaseToolbar } from './components/report-showcase-toolbar'
import { ReportShowcaseList } from './components/report-showcase-list'
import { ReportShowcaseCardGrid } from './components/report-showcase-card-grid'

export function ReportShowcasePage() {
  const rawSearch = useSearch({ strict: false }) as unknown as ShowcaseSearch
  const navigate = useNavigate()
  const { algorithmId: globalAlgorithmId, setAlgorithmId } = useGlobalAlgorithm()

  const search: ShowcaseSearch = {
    ...rawSearch,
    view: rawSearch.view ?? 'table',
    page: rawSearch.page ?? 1,
    pageSize: rawSearch.pageSize ?? 20,
    sortBy: rawSearch.sortBy ?? 'created_at',
    sortOrder: rawSearch.sortOrder ?? 'desc',
  }

  // INT-442：算法大卡写回全局 store → URL 回写保持可分享；URL 显式值（非 'none'）优先，
  // 'none' = 本页解除全局算法（列表不筛选，大卡选中态与之一致）；无显式值回退全局 store。
  const storeAlgorithmType = useMemo(
    () => (globalAlgorithmId ? toReportAlgorithmType(globalAlgorithmId) : undefined),
    [globalAlgorithmId]
  )
  const effectiveAlgorithmType =
    search.algorithmType === 'none'
      ? undefined
      : (search.algorithmType ?? storeAlgorithmType)

  // store→URL 回写：大卡点击（store 变化）后 URL 跟随（''=全部算法 → 'none'）
  const lastStoreTypeRef = useRef(storeAlgorithmType)
  useEffect(() => {
    const prev = lastStoreTypeRef.current
    lastStoreTypeRef.current = storeAlgorithmType
    if (prev === storeAlgorithmType) return
    const next = storeAlgorithmType ?? 'none'
    if (search.algorithmType !== next) {
      void navigate({
        to: '/reports',
        search: (s) => ({ ...s, algorithmType: next, page: 1 }) as unknown as typeof s,
      })
    }
  }, [storeAlgorithmType, search.algorithmType, navigate])

  // URL 'none' 与 store 已选矛盾（store 已选但列表不筛）：仅首次进入页面时置空 store，
  // 令大卡选中态一致；后续大卡点击（store 变化）是用户意图，优先于 URL 'none'（store→URL 回写覆盖）。
  const noneInitializedRef = useRef(false)
  useEffect(() => {
    if (!noneInitializedRef.current) {
      noneInitializedRef.current = true
      if (search.algorithmType === 'none' && globalAlgorithmId) {
        setAlgorithmId(ALL_ALGORITHMS_SENTINEL)
      }
    }
  }, [search.algorithmType, globalAlgorithmId, setAlgorithmId])

  // P3-3：首入时 URL 显式算法值（非 'none'）写回全局 store，保证大卡选中态与列表过滤一致
  const urlExplicitInitializedRef = useRef(false)
  useEffect(() => {
    if (urlExplicitInitializedRef.current) return
    urlExplicitInitializedRef.current = true
    const explicit = search.algorithmType
    if (explicit && explicit !== 'none') {
      const id = toGlobalAlgorithmId(explicit)
      if (id && globalAlgorithmId !== id) setAlgorithmId(id)
    }
  }, [search.algorithmType, globalAlgorithmId, setAlgorithmId])

  const query = useMemo(
    () => buildShowcaseQuery(search, effectiveAlgorithmType),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(search), effectiveAlgorithmType]
  )

  const listQuery = usePublishedReportList(query)
  const items = listQuery.data?.items ?? []
  const total = listQuery.data?.total ?? 0

  const setSearch = useCallback(
    (patch: Record<string, unknown>) => {
      void navigate({
        to: '/reports',
        search: (prev) => ({ ...prev, ...patch }) as unknown as typeof prev,
      })
    },
    [navigate]
  )

  // 搜索框本地态 + 防抖回写 URL
  const [searchInput, setSearchInput] = useState(search.search ?? '')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => {
    setSearchInput(search.search ?? '')
  }, [search.search])
  const handleSearchChange = useCallback(
    (value: string) => {
      setSearchInput(value)
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        setSearch({ search: value || undefined, page: 1 })
      }, 300)
    },
    [setSearch]
  )

  const handleTypeChange = useCallback(
    (type?: ShowcaseSearch['type']) => setSearch({ type, page: 1 }),
    [setSearch]
  )
  const handleTimeRangeChange = useCallback(
    (timeRange?: ShowcaseSearch['timeRange']) =>
      setSearch({ timeRange, startTime: undefined, endTime: undefined, page: 1 }),
    [setSearch]
  )
  const handleCustomRangeChange = useCallback(
    (start?: string, end?: string) =>
      setSearch({ startTime: start || undefined, endTime: end || undefined, page: 1 }),
    [setSearch]
  )
  const handleSortChange = useCallback(
    (sortBy: ShowcaseSearch['sortBy'], sortOrder?: ShowcaseSearch['sortOrder']) => {
      setSearch({
        sortBy,
        sortOrder:
          sortOrder ??
          (sortBy === search.sortBy ? (search.sortOrder === 'asc' ? 'desc' : 'asc') : 'desc'),
        page: 1,
      })
    },
    [setSearch, search.sortBy, search.sortOrder]
  )
  const handleViewModeChange = useCallback(
    (view: 'table' | 'card') => setSearch({ view }),
    [setSearch]
  )

  const hasActiveFilters = useMemo(
    () =>
      Boolean(search.search || search.type || search.timeRange || search.startTime || search.endTime),
    [search]
  )
  const handleClearAll = useCallback(() => {
    setSearch({
      search: undefined,
      type: undefined,
      timeRange: undefined,
      startTime: undefined,
      endTime: undefined,
      page: 1,
    })
  }, [setSearch])

  const handleRowClick = useCallback(
    (report: { id: number }) => {
      void navigate({
        to: '/report/$reportId',
        params: { reportId: String(report.id) },
        search: { from: 'showcase' },
      })
    },
    [navigate]
  )

  return (
    <SectionPageLayout fixedContent>
      <SectionPageLayout.Title>
        <span className='inline-flex items-center gap-2'>
          报告
          <Badge variant='outline' className='font-mono tabular-nums'>
            共 {total} 个已发布报告
          </Badge>
        </span>
      </SectionPageLayout.Title>

      <SectionPageLayout.Content>
        <div className='flex h-full min-h-0 flex-col gap-4 overflow-y-auto pb-4'>
          <ReportShowcaseHero
            search={searchInput}
            onSearchChange={handleSearchChange}
            type={search.type}
            onTypeChange={handleTypeChange}
            timeRange={search.timeRange}
            onTimeRangeChange={handleTimeRangeChange}
            startTime={search.startTime}
            endTime={search.endTime}
            onCustomRangeChange={handleCustomRangeChange}
            hasActiveFilters={hasActiveFilters}
            onClearAll={handleClearAll}
          />

          {/* INT-486 算法卡片网格（INT-442 口径）：写回全局 store，列表自动附 algorithm_type */}
          <AlgorithmCardGrid title='选择算法' />

          <ReportShowcaseToolbar
            filteredCount={total}
            sortBy={search.sortBy}
            sortOrder={search.sortOrder}
            onSortChange={handleSortChange}
            viewMode={search.view}
            onViewModeChange={handleViewModeChange}
          />

          {search.view === 'card' ? (
            <ReportShowcaseCardGrid
              items={items}
              isLoading={listQuery.isLoading}
              hasError={listQuery.isError}
              onRetry={() => void listQuery.refetch()}
              onCardClick={handleRowClick}
            />
          ) : (
            <ReportShowcaseList
              items={items}
              isLoading={listQuery.isLoading}
              hasError={listQuery.isError}
              onRetry={() => void listQuery.refetch()}
              onRowClick={handleRowClick}
            />
          )}

          <ReportsPagination
            page={search.page}
            pageSize={search.pageSize}
            total={total}
            pages={listQuery.data?.pages ?? 1}
            onPageChange={(page) => setSearch({ page })}
            onPageSizeChange={(pageSize) => setSearch({ pageSize, page: 1 })}
          />
        </div>
      </SectionPageLayout.Content>
    </SectionPageLayout>
  )
}

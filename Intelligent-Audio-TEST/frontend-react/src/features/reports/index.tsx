/**
 * /report-center 报告中心·管理页（INT-434 重实施落位；15_报告域.md §2，INT-360 版式保留）。
 * 版式对位 newAPI 模型价格页：Hero 头 + 统计徽章行 + 工具栏 + 数据表/卡片
 * + 收藏/回收站工具条 + 批量浮条 + 分页 + 弹窗群（生成/导出/发布/删除/对比/重命名/进度）。
 * 管理操作集中本页（INT-441 双入口拆分：展示页 /reports 见 features/reports-showcase/）。
 * 口径修正 2026-10-16：取消「测试报告/历史报告」双页签——报告列表单一视图，默认展示全部报告
 * （不限类型）；类型进筛选条件（chips 常驻、默认「全部」）；旧链 /test-reports、/history-reports
 * redirect 到 /report-center 不再带 tab 语义。URL 态全部经 TanStack validateSearch
 * （features/reports/types.ts），页面以 navigate 回写。
 */
import { useNavigate, useSearch } from '@tanstack/react-router'
import { BarChart3, FilePlus2, MoreHorizontal, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useReportList } from '@/application/reports/use-report-list'
import { useReportCounts } from '@/application/reports/use-report-counts'
import { useReportSummaryCounts } from '@/application/reports/use-report-summary-counts'
import {
  useBatchReportActions,
  useReportActions,
} from '@/application/reports/use-report-actions'
import type { ReportListItem } from '@/domain/models/report'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import type { ReportsSearch } from '@/features/reports/types'
import { getLinkedAlgorithmLabel, toReportAlgorithmType } from '@/features/reports/lib/algorithm'
import { buildReportListQuery } from '@/features/reports/lib/search'

import { ReportHero } from './components/report-hero'
import { ReportAdvancedSearch } from './components/report-advanced-search'
import { ReportStatsRow, type BadgeKind } from './components/report-stats-row'
import { ReportFilterToolbar } from './components/report-filter-toolbar'
import { ReportsTable } from './components/reports-table'
import { ReportCardGrid } from './components/report-card-grid'
import { ReportFavoriteTrashBar } from './components/report-favorite-trash-bar'
import { ReportsPagination } from './components/reports-pagination'
import type { ReportRowAction } from './components/report-row-actions'
import { GenerateReportDialog } from './components/modals/generate-report-dialog'
import { ExportReportDialog } from './components/modals/export-report-dialog'
import { ReportCompareDialog } from './components/modals/report-compare-dialog'
import { ReportRenameDialog } from './components/modals/report-rename-dialog'
import { ReportProgressDialog } from './components/modals/report-progress-dialog'
import {
  BatchConfirmDialog,
  DeleteReportDialog,
  PublishReportDialog,
  PurgeReportDialog,
} from './components/modals/report-confirm-dialogs'

export function ReportCenterPage() {
  const rawSearch = useSearch({ strict: false }) as unknown as ReportsSearch
  const navigate = useNavigate()
  const { hasPermission } = usePermissions()
  const globalAlgorithmId = useAlgorithmStore((s) => s.algorithmId)
  const reportActions = useReportActions()
  const batchActions = useBatchReportActions()
  const summaryCountsQuery = useReportSummaryCounts()
  const typeCounts = summaryCountsQuery.data?.typeCounts ?? {
    all: 0,
    task: 0,
    comparison: 0,
    secondary_comparison: 0,
    benchmark: 0,
  }
  const favoriteCount = summaryCountsQuery.data?.favoriteCount ?? 0

  const search: ReportsSearch = {
    ...rawSearch,
    view: rawSearch.view ?? 'table',
    page: rawSearch.page ?? 1,
    pageSize: rawSearch.pageSize ?? 20,
    favorite: rawSearch.favorite ?? false,
    trash: rawSearch.trash ?? false,
    sortBy: rawSearch.sortBy ?? 'created_at',
    sortOrder: rawSearch.sortOrder ?? 'desc',
  }

  // 全局算法联动（规范 §2.2）：URL 无 algorithmType 时自动附全局；'none' 为「本页临时解除」
  const linkedAlgorithmType = useMemo(
    () => toReportAlgorithmType(globalAlgorithmId),
    [globalAlgorithmId]
  )
  const effectiveAlgorithmType =
    search.algorithmType === 'none'
      ? undefined
      : (search.algorithmType ?? linkedAlgorithmType)

  const query = useMemo(
    () => ({
      ...buildReportListQuery(search),
      algorithm_type: effectiveAlgorithmType,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(search), effectiveAlgorithmType]
  )

  const listQuery = useReportList(query)
  const countsQuery = useReportCounts()
  const items = listQuery.data?.items ?? []
  const total = listQuery.data?.total ?? 0

  const setSearch = useCallback(
    (patch: Record<string, unknown>) => {
      void navigate({
        to: '/report-center',
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
        setSearch({
          search: value || undefined,
          page: 1,
        })
      }, 300)
    },
    [setSearch]
  )

  const handleQuickFilter = useCallback(
    (kind: BadgeKind) => {
      // 口径修正 2026-10-16：快速筛选只写筛选条件（status/type），不切页签
      if (kind === 'all') setSearch({ status: undefined, type: undefined, page: 1 })
      else if (kind === 'published') setSearch({ status: 'published', type: undefined, page: 1 })
      else if (kind === 'draft') setSearch({ status: 'draft', type: undefined, page: 1 })
      else setSearch({ status: undefined, type: 'comparison', page: 1 })
    },
    [setSearch]
  )

  const handleSortChange = useCallback(
    (sortBy: ReportsSearch['sortBy'], sortOrder?: ReportsSearch['sortOrder']) => {
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

  const handleClearAlgorithm = useCallback(
    () => setSearch({ algorithmType: 'none', page: 1 }),
    [setSearch]
  )

  const hasActiveFilters = useMemo(() => {
    const s = search
    return Boolean(
      s.search ||
        s.type ||
        s.status ||
        s.timeRange ||
        s.startTime ||
        s.endTime ||
        s.taskType ||
        s.deviceType ||
        s.creator ||
        effectiveAlgorithmType
    )
  }, [search, effectiveAlgorithmType])

  const handleClearAll = useCallback(() => {
    setSearch({
      search: undefined,
      type: undefined,
      status: undefined,
      timeRange: undefined,
      startTime: undefined,
      endTime: undefined,
      taskType: undefined,
      deviceType: undefined,
      creator: undefined,
      algorithmType: undefined,
      favorite: false,
      trash: false,
      page: 1,
    })
  }, [setSearch])

  const handleAdvancedChange = useCallback(
    (patch: { taskType?: string; deviceType?: string; creator?: string }) => {
      setSearch({ ...patch, page: 1 })
    },
    [setSearch]
  )

  // 勾选状态（查询变化时重置）
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  useEffect(() => {
    setSelectedIds([])
  }, [search.page, search.pageSize, JSON.stringify(search.search), search.type, search.status, search.timeRange, effectiveAlgorithmType])

  const handleToggleRow = useCallback((id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }, [])
  const handleToggleAll = useCallback(() => {
    setSelectedIds((prev) =>
      prev.length === items.length && items.every((i) => prev.includes(i.id))
        ? []
        : items.map((i) => i.id)
    )
  }, [items])

  // 弹窗状态
  const [generateOpen, setGenerateOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [exportCount, setExportCount] = useState(1)
  const [exportScope, setExportScope] = useState('')
  const [publishTarget, setPublishTarget] = useState<ReportListItem>()
  const [deleteTarget, setDeleteTarget] = useState<ReportListItem>()
  const [purgeTarget, setPurgeTarget] = useState<ReportListItem>()
  const [renameTarget, setRenameTarget] = useState<ReportListItem>()
  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false)
  const [batchPurgeOpen, setBatchPurgeOpen] = useState(false)
  const [compareOpen, setCompareOpen] = useState(false)
  const [progressOpen, setProgressOpen] = useState(false)
  const [progressReportId, setProgressReportId] = useState(0)

  const selectedReports = useMemo(
    () => items.filter((i) => selectedIds.includes(i.id)),
    [items, selectedIds]
  )

  const handleRowAction = useCallback(
    (report: ReportListItem, action: ReportRowAction) => {
      if (action === 'view') {
        void navigate({
          to: '/report/$reportId',
          params: { reportId: String(report.id) },
          search: { from: 'management' },
        })
      } else if (action === 'edit') {
        setRenameTarget(report)
      } else if (action === 'publish') {
        setPublishTarget(report)
      } else if (action === 'delete') {
        setDeleteTarget(report)
      } else if (action === 'favorite') {
        void reportActions.toggleFavorite(report.id, !report.is_favorite)
      } else if (action === 'restore') {
        void reportActions.restore([report.id])
      } else if (action === 'purge') {
        setPurgeTarget(report)
      }
    },
    [navigate, reportActions]
  )

  const openExportDialog = useCallback(
    (count: number, scope: string) => {
      setExportCount(count)
      setExportScope(scope)
      setExportOpen(true)
    },
    []
  )

  const handleProgressComplete = useCallback(
    (reportId: number) => {
      setProgressOpen(false)
      void navigate({
        to: '/report/$reportId',
        params: { reportId: String(reportId) },
        search: { from: 'management' },
      })
    },
    [navigate]
  )

  const trashMode = search.trash ?? false
  const favoriteOnly = search.favorite ?? false

  return (
    <SectionPageLayout fixedContent>
      <SectionPageLayout.Title>
        <span className='inline-flex items-center gap-2'>
          报告中心
          <Badge variant='outline' className='font-mono tabular-nums'>
            共 {countsQuery.data?.all ?? 0} 个报告
          </Badge>
        </span>
      </SectionPageLayout.Title>
      <SectionPageLayout.Actions>
        {hasPermission('report:create') && (
          <Button size='sm' onClick={() => setGenerateOpen(true)}>
            <FilePlus2 data-icon='inline-start' />
            生成报告
          </Button>
        )}
        <DropdownMenu modal={false}>
          <DropdownMenuTrigger
            render={<Button variant='ghost' size='sm' aria-label='更多操作' />}
          >
            <MoreHorizontal className='size-4' />
          </DropdownMenuTrigger>
          <DropdownMenuContent align='end' className='w-44'>
            <DropdownMenuItem
              onClick={() => void navigate({ to: '/report-statistics' })}
            >
              <BarChart3 className='size-4' />
              统计分析
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => {
                if (selectedIds.length > 0) {
                  openExportDialog(selectedIds.length, `已选择 ${selectedIds.length} 个报告`)
                } else {
                  openExportDialog(items.length, '当前筛选列表全部报告')
                }
              }}
            >
              导出 CSV
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => void listQuery.refetch()}>
              <RefreshCw className='size-4' />
              刷新
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SectionPageLayout.Actions>

      <SectionPageLayout.Content>
        <div className='flex h-full min-h-0 flex-col gap-4 overflow-y-auto pb-4'>
          <ReportHero
            totalReports={countsQuery.data?.all ?? 0}
            draftCount={countsQuery.data?.draft ?? 0}
            publishedCount={countsQuery.data?.published ?? 0}
            typeCounts={typeCounts}
            search={searchInput}
            onSearchChange={handleSearchChange}
            type={search.type}
            onTypeChange={(value) => setSearch({ type: value, page: 1 })}
            status={search.status}
            onStatusChange={(value) => setSearch({ status: value, page: 1 })}
            timeRange={search.timeRange}
            onTimeRangeChange={(value) =>
              setSearch({ timeRange: value, startTime: undefined, endTime: undefined, page: 1 })
            }
            startTime={search.startTime}
            endTime={search.endTime}
            onCustomRangeChange={(start, end) =>
              setSearch({ startTime: start, endTime: end, page: 1 })
            }
            hasActiveFilters={hasActiveFilters}
            onClearAll={handleClearAll}
          />

          {/* 高级搜索（任务类型 × 设备类型 × 创建者，§2 实测 :173-193；INT-381 返修） */}
          <ReportAdvancedSearch
            taskType={search.taskType}
            deviceType={search.deviceType}
            creator={search.creator}
            onChange={handleAdvancedChange}
            onReset={() => setSearch({ taskType: undefined, deviceType: undefined, creator: undefined, page: 1 })}
          />

          <ReportStatsRow
            counts={countsQuery.data}
            isLoading={countsQuery.isLoading}
            activeFilter={{ status: search.status, type: search.type }}
            onQuickFilter={handleQuickFilter}
          />

          <ReportFilterToolbar
            filteredCount={total}
            totalCount={countsQuery.data?.all ?? 0}
            sortBy={search.sortBy ?? 'created_at'}
            sortOrder={search.sortOrder ?? 'desc'}
            onSortChange={handleSortChange}
            viewMode={search.view ?? 'table'}
            onViewModeChange={handleViewModeChange}
            linkedAlgorithm={
              effectiveAlgorithmType
                ? (getLinkedAlgorithmLabel(globalAlgorithmId) ??
                  effectiveAlgorithmType)
                : undefined
            }
            onClearAlgorithm={handleClearAlgorithm}
          />

          <ReportFavoriteTrashBar
            favoriteOnly={favoriteOnly}
            trashMode={trashMode}
            favoriteCount={favoriteCount}
            onFavoriteOnlyChange={(value) => setSearch({ favorite: value, page: 1 })}
            onTrashModeChange={(value) => setSearch({ trash: value, page: 1 })}
          />

          {search.view === 'card' ? (
            <ReportCardGrid
              items={items}
              isLoading={listQuery.isLoading}
              hasError={listQuery.isError}
              totalCount={total}
              trashMode={trashMode}
              hasPermission={hasPermission}
              onRowAction={handleRowAction}
              onCardClick={(report) => handleRowAction(report, 'view')}
              onClearFilters={handleClearAll}
              onRetry={() => void listQuery.refetch()}
              emptyAction={
                hasPermission('report:create') ? (
                  <Button variant='secondary' size='sm' onClick={() => setGenerateOpen(true)}>
                    <FilePlus2 data-icon='inline-start' />
                    生成报告
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <ReportsTable
              items={items}
              isLoading={listQuery.isLoading}
              hasError={listQuery.isError}
              totalCount={total}
              trashMode={trashMode}
              selectedIds={selectedIds}
              onToggleRow={handleToggleRow}
              onToggleAll={handleToggleAll}
              hasPermission={hasPermission}
              onRowAction={handleRowAction}
              onRowClick={(report) => handleRowAction(report, 'view')}
              onClearFilters={handleClearAll}
              onRetry={() => void listQuery.refetch()}
            />
          )}

          <ReportsPagination
            page={search.page ?? 1}
            pageSize={search.pageSize ?? 20}
            total={total}
            pages={listQuery.data?.pages ?? 1}
            onPageChange={(page) => setSearch({ page })}
            onPageSizeChange={(pageSize) => setSearch({ pageSize, page: 1 })}
          />

          {/* 批量操作浮条 */}
          {selectedIds.length > 0 && (
            <div className='fixed bottom-6 left-1/2 z-50 w-max max-w-[calc(100vw-2rem)] -translate-x-1/2'>
              <div className='bg-background/95 supports-[backdrop-filter]:bg-background/60 p-2 shadow-xl rounded-xl border backdrop-blur-lg flex flex-wrap items-center gap-2'>
                <Badge className='min-w-8 justify-center rounded-lg font-mono tabular-nums'>
                  {selectedIds.length}
                </Badge>
                <span className='text-muted-foreground pr-1 text-sm'>
                  已选择 {selectedIds.length} 个报告
                </span>
                {!trashMode && hasPermission('report:compare') && (
                  <Button variant='secondary' size='sm' onClick={() => setCompareOpen(true)}>
                    批量对比
                  </Button>
                )}
                {trashMode ? (
                  hasPermission('report:delete') && (
                    <>
                      <Button size='sm' onClick={() => void batchActions.batchRestore(selectedIds)}>
                        批量恢复
                      </Button>
                      <Button
                        variant='destructive'
                        size='sm'
                        onClick={() => setBatchPurgeOpen(true)}
                      >
                        彻底删除
                      </Button>
                    </>
                  )
                ) : (
                  hasPermission('report:delete') && (
                    <Button variant='destructive' size='sm' onClick={() => setBatchDeleteOpen(true)}>
                      批量删除
                    </Button>
                  )
                )}
                <Button variant='ghost' size='sm' onClick={() => setSelectedIds([])}>
                  取消选择
                </Button>
              </div>
            </div>
          )}
        </div>
      </SectionPageLayout.Content>

      {/* 弹窗群 */}
      <GenerateReportDialog
        open={generateOpen}
        onOpenChange={setGenerateOpen}
        onGenerated={(id) => {
          setProgressReportId(id)
          setProgressOpen(true)
        }}
      />
      <ExportReportDialog
        open={exportOpen}
        onOpenChange={setExportOpen}
        scope={exportScope}
        count={exportCount}
        onExport={(format) => reportActions.exportReport(selectedIds.length ? selectedIds : (items.map((i) => i.id)), format)}
      />
      <ReportCompareDialog
        open={compareOpen}
        onOpenChange={setCompareOpen}
        selectedReports={selectedReports}
        onCompared={(id) => {
          setSelectedIds([])
          setProgressReportId(id)
          setProgressOpen(true)
        }}
      />
      <ReportRenameDialog
        open={renameTarget !== undefined}
        onOpenChange={(open) => {
          if (!open) setRenameTarget(undefined)
        }}
        report={renameTarget}
        onConfirm={(report, payload) => void reportActions.rename(report.id, payload)}
      />
      <PublishReportDialog
        open={publishTarget !== undefined}
        onOpenChange={(open) => {
          if (!open) setPublishTarget(undefined)
        }}
        report={publishTarget}
        onConfirm={(report) => {
          setPublishTarget(undefined)
          void reportActions.publish(report.id)
        }}
      />
      <DeleteReportDialog
        open={deleteTarget !== undefined}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(undefined)
        }}
        report={deleteTarget}
        onConfirm={(report) => {
          setDeleteTarget(undefined)
          void reportActions.softDelete([report.id])
        }}
      />
      <PurgeReportDialog
        open={purgeTarget !== undefined}
        onOpenChange={(open) => {
          if (!open) setPurgeTarget(undefined)
        }}
        report={purgeTarget}
        onConfirm={(report) => {
          setPurgeTarget(undefined)
          void reportActions.purge([report.id])
        }}
      />
      <BatchConfirmDialog
        open={batchDeleteOpen}
        onOpenChange={setBatchDeleteOpen}
        title='批量删除'
        desc={`将把已选择的 ${selectedIds.length} 个报告移入回收站。`}
        confirmText='删除'
        destructive
        onConfirm={() => {
          setBatchDeleteOpen(false)
          void batchActions.batchDelete(selectedIds).then(() => setSelectedIds([]))
        }}
      />
      <BatchConfirmDialog
        open={batchPurgeOpen}
        onOpenChange={setBatchPurgeOpen}
        title='批量彻底删除'
        desc={`将永久删除已选择的 ${selectedIds.length} 个报告及其全部报告数据，此操作不可恢复。`}
        confirmText='彻底删除'
        destructive
        onConfirm={() => {
          setBatchPurgeOpen(false)
          void batchActions.batchPurge(selectedIds).then(() => setSelectedIds([]))
        }}
      />
      <ReportProgressDialog
        open={progressOpen}
        onOpenChange={setProgressOpen}
        reportId={progressReportId}
        onComplete={handleProgressComplete}
      />
    </SectionPageLayout>
  )
}

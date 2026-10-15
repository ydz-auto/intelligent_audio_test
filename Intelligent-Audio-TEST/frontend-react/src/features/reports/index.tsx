/**
 * /reports 报告中心（INT-434 落位；规范 §3）。
 * 版式对位 newAPI 模型价格页：双页签 + Hero 头 + 统计徽章行 + 工具栏 + 数据表/卡片
 * + 收藏/回收站工具条 + 批量浮条 + 分页 + 弹窗群（生成/导出/发布/删除/对比/重命名/进度）。
 * URL 态全部经 TanStack validateSearch（features/reports/types.ts），页面以 navigate 回写。
 */
import { useNavigate, useSearch } from '@tanstack/react-router'
import { FilePlus2, MoreHorizontal, RefreshCw } from 'lucide-react'
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
import { useReportTabCounts } from '@/application/reports/use-tab-counts'
import {
  useBatchReportActions,
  useReportActions,
} from '@/application/reports/use-report-actions'
import type { ReportListItem } from '@/domain/models/report'
import {
  MOCK_REPORT_LIST_ITEMS,
} from '@/infrastructure/mock/reports-mock'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { resolveReportUiFlags } from '@/infrastructure/stores/reports-ui-store'
import type { ReportsSearch } from '@/features/reports/types'
import { getLinkedAlgorithmLabel, toReportAlgorithmType } from '@/features/reports/lib/algorithm'
import { buildReportListQuery } from '@/features/reports/lib/search'

import { ReportTabs } from './components/report-tabs'
import { ReportHero } from './components/report-hero'
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

/** Hero 类型 chips 计数（mock 全量，剔除回收站项；演示用） */
function useReportTypeCounts() {
  return useMemo(() => {
    const items = MOCK_REPORT_LIST_ITEMS.filter((item) => {
      const flags = resolveReportUiFlags(item.id, item.is_favorite)
      return !flags.deleted
    })
    return {
      all: items.length,
      task: items.filter((i) => i.type === 'task').length,
      comparison: items.filter((i) => i.type === 'comparison').length,
      secondary_comparison: items.filter((i) => i.type === 'secondary_comparison').length,
    }
  }, [])
}

export function ReportCenterPage() {
  const rawSearch = useSearch({ strict: false }) as unknown as ReportsSearch
  const navigate = useNavigate()
  const { hasPermission } = usePermissions()
  const globalAlgorithmId = useAlgorithmStore((s) => s.algorithmId)
  const reportActions = useReportActions()
  const batchActions = useBatchReportActions()
  const typeCounts = useReportTypeCounts()

  const tab: 'test' | 'history' = rawSearch.tab ?? 'history'
  const search: ReportsSearch = { ...rawSearch, tab }

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
      ...buildReportListQuery(search, tab),
      algorithm_type: effectiveAlgorithmType,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(search), tab, effectiveAlgorithmType]
  )

  const listQuery = useReportList(query)
  const tabCountsQuery = useReportTabCounts()
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
        setSearch({
          search: value || undefined,
          page: 1,
        })
      }, 300)
    },
    [setSearch]
  )

  const handleTabChange = useCallback(
    (next: 'test' | 'history') => setSearch({ tab: next, page: 1 }),
    [setSearch]
  )

  const handleQuickFilter = useCallback(
    (kind: BadgeKind) => {
      if (kind === 'all') setSearch({ tab: 'history', status: undefined, type: undefined, page: 1 })
      else if (kind === 'published') setSearch({ tab: 'history', status: 'published', type: undefined, page: 1 })
      else if (kind === 'draft') setSearch({ tab: 'history', status: 'draft', type: undefined, page: 1 })
      else setSearch({ tab: 'history', status: undefined, type: 'comparison', page: 1 })
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
      algorithmType: undefined,
      favorite: false,
      trash: false,
      page: 1,
    })
  }, [setSearch])

  // 勾选状态（查询变化/页签切换重置）
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  useEffect(() => {
    setSelectedIds([])
  }, [tab, search.page, search.pageSize, JSON.stringify(search.search), search.type, search.status, search.timeRange, effectiveAlgorithmType])

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
      })
    },
    [navigate]
  )

  const favoriteCount = useMemo(() => {
    return MOCK_REPORT_LIST_ITEMS.filter((item) => {
      const flags = resolveReportUiFlags(item.id, item.is_favorite)
      return flags.isFavorite && !flags.deleted
    }).length
  }, [])
  const trashMode = search.trash ?? false
  const favoriteOnly = search.favorite ?? false

  return (
    <SectionPageLayout fixedContent>
      <SectionPageLayout.Title>
        <span className='inline-flex items-center gap-2'>
          报告中心
          <Badge variant='outline' className='font-mono tabular-nums'>
            共 {tabCountsQuery.data?.all ?? 0} 个报告
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
              onClick={() =>
                openExportDialog(items.length, '当前筛选列表全部报告')
              }
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
          <ReportTabs value={tab} onChange={handleTabChange} />

          <ReportHero
            tab={tab}
            totalReports={tabCountsQuery.data?.all ?? 0}
            draftCount={tabCountsQuery.data?.draft ?? 0}
            publishedCount={tabCountsQuery.data?.published ?? 0}
            typeCounts={typeCounts}
            search={searchInput}
            onSearchChange={handleSearchChange}
            type={tab === 'test' ? undefined : search.type}
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

          <ReportStatsRow
            counts={tabCountsQuery.data}
            isLoading={tabCountsQuery.isLoading}
            activeFilter={
              tab === 'test'
                ? undefined
                : { status: search.status, type: search.type }
            }
            onQuickFilter={handleQuickFilter}
          />

          <ReportFilterToolbar
            filteredCount={total}
            totalCount={tabCountsQuery.data?.all ?? 0}
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

          {tab === 'history' && !trashMode && (
            <ReportFavoriteTrashBar
              favoriteOnly={favoriteOnly}
              trashMode={trashMode}
              favoriteCount={favoriteCount}
              onFavoriteOnlyChange={(value) => setSearch({ favorite: value, page: 1 })}
              onTrashModeChange={(value) => setSearch({ trash: value, page: 1 })}
            />
          )}

          {search.view === 'card' && !listQuery.isLoading ? (
            <ReportCardGrid
              items={items}
              trashMode={trashMode}
              hasPermission={hasPermission}
              onRowAction={handleRowAction}
              onCardClick={(report) => handleRowAction(report, 'view')}
            />
          ) : (
            <ReportsTable
              items={items}
              isLoading={listQuery.isLoading}
              totalCount={total}
              trashMode={trashMode}
              selectedIds={selectedIds}
              onToggleRow={handleToggleRow}
              onToggleAll={handleToggleAll}
              hasPermission={hasPermission}
              onRowAction={handleRowAction}
              onRowClick={(report) => handleRowAction(report, 'view')}
              onClearFilters={handleClearAll}
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
                {tab === 'history' && !trashMode && hasPermission('report:compare') && (
                  <Button variant='secondary' size='sm' onClick={() => setCompareOpen(true)}>
                    批量对比
                  </Button>
                )}
                {trashMode ? (
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

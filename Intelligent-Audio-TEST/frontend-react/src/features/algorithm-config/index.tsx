/**
 * 算法配置页（17_配置运维.md §3；models/channels 表格版式对位）。
 * SectionPageLayout fixedContent + Title 徽标 + 页头动作区 + 筛选工具条 + DataTable + 分页 Portal。
 * 全局算法切换器联动（§2.2）：数据源同 GET /algorithm/definitions，当前全局算法行高亮。
 * 弹窗群：详情 Dialog / 编辑 Sheet / 分组管理 / 导入 / 复制·删除·重载·批量删除 ConfirmDialog。
 */
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { PageFooterPortal } from '@/components/layout/components/page-footer'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import {
  useAlgorithmDefinitions,
  useAlgorithmDimensionOptions,
  useAlgorithmGroups,
  useAlgorithmMutations,
} from '@/application/algorithm-config/useAlgorithmDefinitions'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { usePermissions } from '@/application/hooks/use-permissions'
import { toast } from 'sonner'
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { AlgorithmDefinition } from '@/domain/models/algorithmConfig'
import {
  ALGORITHM_SEARCH_DEBOUNCE_MS,
  DEFAULT_PAGE_SIZE,
  PAGE_SIZE_OPTIONS,
} from '@/features/algorithm-config/constants'
import { AlgorithmPrimaryButtons } from '@/features/algorithm-config/components/algorithm-primary-buttons'
import { AlgorithmFilterToolbar } from '@/features/algorithm-config/components/algorithm-filter-toolbar'
import { AlgorithmsTable } from '@/features/algorithm-config/components/algorithms-table'
import { AlgorithmDetailDialog } from '@/features/algorithm-config/components/modals/algorithm-detail-dialog'
import { AlgorithmGroupManagerDialog } from '@/features/algorithm-config/components/modals/algorithm-group-manager-dialog'
import { AlgorithmImportDialog } from '@/features/algorithm-config/components/modals/algorithm-import-dialog'
import { AlgorithmConfirmDialogs } from '@/features/algorithm-config/components/modals/algorithm-confirm-dialogs'
import { AlgorithmMutateSheet } from '@/features/algorithm-config/mutate/algorithm-mutate-sheet'
import type {
  AlgorithmConfirmState,
  DetailDialogState,
  MutateSheetState,
} from '@/features/algorithm-config/types'

/** 300ms 防抖搜索（§3.4 搜索提交） */
function useDebouncedSearch(initial = '') {
  const [value, setValue] = useState(initial)
  const [committed, setCommitted] = useState(initial)
  const timerRef = useRef<number | null>(null)

  const handleChange = useCallback((next: string) => {
    setValue(next)
    if (timerRef.current) window.clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(
      () => setCommitted(next.trim().toLowerCase()),
      ALGORITHM_SEARCH_DEBOUNCE_MS
    )
  }, [])

  return [value, handleChange, committed] as const
}

export function AlgorithmConfigPage() {
  const { hasPermission } = usePermissions()
  const canManage = hasPermission('algorithm:definition_manage')
  const canGroupManage = hasPermission('algorithm:group_manage')

  const definitionsQuery = useAlgorithmDefinitions()
  const groupsQuery = useAlgorithmGroups()
  const dimensionOptionsQuery = useAlgorithmDimensionOptions()
  const { remove, bulkRemove, reload } = useAlgorithmMutations()

  const globalAlgorithmType = useAlgorithmStore((s) => s.algorithmId)

  // URL 态语义（§3.2 mock 阶段本地态；接线后 validateSearch 化）
  const [searchInput, handleSearch, searchKeyword] = useDebouncedSearch()
  const [groupFilter, setGroupFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())

  // 搜索关键词提交时回到第一页（§3.4 与分组/状态 facet 口径一致，避免分页指示错位）
  useEffect(() => {
    setPage(1)
  }, [searchKeyword])

  // 弹窗群
  const [mutateSheet, setMutateSheet] = useState<MutateSheetState>({
    open: false,
    mode: 'create',
    algorithm: null,
  })
  const [detailDialog, setDetailDialog] = useState<DetailDialogState>({
    open: false,
    algorithm: null,
  })
  const [groupManagerOpen, setGroupManagerOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [confirm, setConfirm] = useState<AlgorithmConfirmState>(null)
  const [confirmPending, setConfirmPending] = useState(false)

  const definitions = definitionsQuery.data ?? []
  const groups = groupsQuery.data ?? []

  /* ───────── 过滤 / 排序 / 分页（§3.4 + §3.7 前端分页） ───────── */

  const filtered = useMemo(() => {
    let rows = definitions
    if (searchKeyword) {
      rows = rows.filter(
        (row) =>
          row.type.toLowerCase().includes(searchKeyword) ||
          row.name.toLowerCase().includes(searchKeyword)
      )
    }
    if (groupFilter !== 'all') {
      rows = rows.filter((row) => String(row.groupId) === groupFilter)
    }
    if (statusFilter !== 'all') {
      rows = rows.filter((row) => row.status === statusFilter)
    }
    return rows
  }, [definitions, searchKeyword, groupFilter, statusFilter])

  const sorted = useMemo(() => {
    const rows = [...filtered]
    rows.sort((a, b) => {
      const diff = new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
      return sortOrder === 'desc' ? diff : -diff
    })
    return rows
  }, [filtered, sortOrder])

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize))
  const safePage = Math.min(page, pageCount)
  const pageRows = useMemo(
    () => sorted.slice((safePage - 1) * pageSize, safePage * pageSize),
    [sorted, safePage, pageSize]
  )

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      if (pageRows.length > 0 && prev.size === pageRows.length) return new Set()
      return new Set(pageRows.map((row) => row.id))
    })
  }

  const selectedTypes = useMemo(
    () =>
      definitions
        .filter((row) => selectedIds.has(row.id))
        .map((row) => row.type),
    [definitions, selectedIds]
  )

  const openCreate = () => setMutateSheet({ open: true, mode: 'create', algorithm: null })
  const openEdit = (algorithm: AlgorithmDefinition) =>
    setMutateSheet({ open: true, mode: 'edit', algorithm })
  const openClone = (algorithm: AlgorithmDefinition) =>
    setConfirm({ kind: 'clone', algorithm })

  /* ───────── 导出（§7.14：getDefinitions() 全量 → JSON Blob 下载） ───────── */

  const handleExport = () => {
    // 接线后数据源 = 查询缓存全量（原 mock peekAlgorithmDefinitions 退役）
    const data = definitions
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    const date = new Date().toISOString().slice(0, 10)
    anchor.href = url
    anchor.download = `algorithms_${date}.json`
    anchor.click()
    URL.revokeObjectURL(url)
    toast.success('配置已导出')
  }

  /* ───────── 确认弹窗分派（§7.4/7.5/7.7/7.8） ───────── */

  const handleConfirm = async () => {
    if (!confirm) return
    setConfirmPending(true)
    try {
      if (confirm.kind === 'clone') {
        setMutateSheet({ open: true, mode: 'clone', algorithm: confirm.algorithm })
        setConfirm(null)
        return
      }
      if (confirm.kind === 'delete') {
        const result = await remove.mutateAsync(confirm.algorithm.type)
        if (result.success) toast.success('算法已删除')
        else toast.error(result.message ?? '删除失败，请重试')
      } else if (confirm.kind === 'reload') {
        await reload.mutateAsync()
        toast.success('配置已重载')
      } else if (confirm.kind === 'bulk-delete') {
        const result = await bulkRemove.mutateAsync(confirm.types)
        toast.success(`成功删除 ${result.successCount} 个算法，失败 ${result.failedCount} 个`)
        setSelectedIds(new Set())
      }
      setConfirm(null)
    } catch {
      toast.error('操作失败，请重试')
      setConfirm(null)
    } finally {
      setConfirmPending(false)
    }
  }

  const handleBulkDeleteAction = () => {
    if (selectedIds.size === 0) {
      toast.info('请先勾选需要删除的算法')
      return
    }
    setConfirm({
      kind: 'bulk-delete',
      types: selectedTypes,
      count: selectedIds.size,
    })
  }

  /* ───────── 页面装配（§3.1 骨架） ───────── */

  return (
    <>
      <SectionPageLayout fixedContent>
        <SectionPageLayout.Title>
          <span className='flex flex-wrap items-center gap-2'>
            算法配置
            <Badge variant='outline' className='font-normal tabular-nums'>
              共 {definitions.length} 个算法
            </Badge>
          </span>
        </SectionPageLayout.Title>

        <SectionPageLayout.Actions>
          <AlgorithmPrimaryButtons
            canManage={canManage}
            canGroupManage={canGroupManage}
            onNew={openCreate}
            onGroupManage={() => setGroupManagerOpen(true)}
            onImport={() => setImportOpen(true)}
            onExport={handleExport}
            onReload={() => setConfirm({ kind: 'reload' })}
            onBulkDelete={handleBulkDeleteAction}
          />
        </SectionPageLayout.Actions>

        <SectionPageLayout.Content>
          <div className='flex h-full min-h-0 flex-col gap-3'>
            <AlgorithmFilterToolbar
              searchValue={searchInput}
              onSearch={handleSearch}
              groups={groups}
              groupFilter={groupFilter}
              onGroupFilter={(value) => {
                setGroupFilter(value)
                setPage(1)
              }}
              statusFilter={statusFilter}
              onStatusFilter={(value) => {
                setStatusFilter(value)
                setPage(1)
              }}
            />

            <div className='min-h-0 flex-1 overflow-y-auto'>
              <AlgorithmsTable
                rows={pageRows}
                loading={definitionsQuery.isLoading}
                total={filtered.length}
                searchKeyword={searchKeyword}
                selectedIds={selectedIds}
                onToggleSelect={toggleSelect}
                onToggleSelectAll={toggleSelectAll}
                canManage={canManage}
                globalAlgorithmType={globalAlgorithmType}
                sortOrder={sortOrder}
                onSortChange={() =>
                  setSortOrder((prev) => (prev === 'desc' ? 'asc' : 'desc'))
                }
                onEmptyCreate={openCreate}
                onDetail={(algorithm) => setDetailDialog({ open: true, algorithm })}
                onEdit={openEdit}
                onClone={openClone}
                onDelete={(algorithm) => setConfirm({ kind: 'delete', algorithm })}
              />
            </div>

            {/* 批量浮条（§3.7：勾选≥1 浮起） */}
            {selectedIds.size > 0 && canManage && (
              <div className='shadow-xl flex items-center justify-between gap-2 rounded-xl border bg-background/95 p-2 backdrop-blur-lg'>
                <span className='text-muted-foreground px-1 text-sm tabular-nums'>
                  已选择 {selectedIds.size} 个算法
                </span>
                <Button
                  variant='destructive'
                  size='sm'
                  onClick={handleBulkDeleteAction}
                >
                  批量删除
                </Button>
              </div>
            )}

            {/* 分页 Portal（§3.7 PageFooterPortal；须在 SectionPageLayout Provider 子树内） */}
            <PageFooterPortal>
              <PaginationBar
                page={safePage}
                pageCount={pageCount}
                pageSize={pageSize}
                total={sorted.length}
                onPageChange={setPage}
                onPageSizeChange={(size) => {
                  setPageSize(size)
                  setPage(1)
                }}
              />
            </PageFooterPortal>
          </div>
        </SectionPageLayout.Content>
      </SectionPageLayout>

      {/* 弹窗群（§7 Context Provider 挂页级） */}
      <AlgorithmMutateSheet
        open={mutateSheet.open}
        onOpenChange={(open) =>
          setMutateSheet((prev) => ({ ...prev, open, algorithm: open ? prev.algorithm : null }))
        }
        mode={mutateSheet.mode}
        algorithm={mutateSheet.algorithm}
        groups={groups}
        dimensionOptions={dimensionOptionsQuery.data ?? []}
      />
      <AlgorithmDetailDialog
        open={detailDialog.open}
        onOpenChange={(open) => setDetailDialog((prev) => ({ ...prev, open, algorithm: open ? prev.algorithm : null }))}
        algorithm={detailDialog.algorithm}
      />
      <AlgorithmGroupManagerDialog
        open={groupManagerOpen}
        onOpenChange={setGroupManagerOpen}
        groups={groups}
        canManage={canGroupManage}
      />
      <AlgorithmImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        onImported={() => {
          // 导入成功后列表重拉（mock 阶段内存库变更，查询失效）
          void definitionsQuery.refetch()
        }}
      />
      <AlgorithmConfirmDialogs
        state={confirm}
        onOpenChange={(open) => !open && setConfirm(null)}
        onConfirm={handleConfirm}
        pending={confirmPending}
      />
    </>
  )
}

/* ───────────────────────── 分页条（§3.7） ───────────────────────── */

function PaginationBar({
  page,
  pageCount,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: {
  page: number
  pageCount: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
}) {
  return (
    <div className='flex flex-wrap items-center justify-end gap-2 text-sm'>
      {/* §3.7/§10 页码与计数展示「共 {n} 个算法 · {page}/{pageCount} 页」 */}
      <span className='text-muted-foreground tabular-nums'>
        共 {total} 个算法 · {page}/{pageCount} 页
      </span>
      <Select
        value={String(pageSize)}
        onValueChange={(value) => onPageSizeChange(Number(value ?? DEFAULT_PAGE_SIZE))}
      >
        <SelectTrigger size='sm' className='w-24'>
          <SelectValue>{pageSize} 条/页</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {PAGE_SIZE_OPTIONS.map((size) => (
            <SelectItem key={size} value={String(size)}>
              {size} 条/页
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div className='flex items-center gap-1'>
        <Button
          variant='outline'
          size='sm'
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          上一页
        </Button>
        <Button
          variant='outline'
          size='sm'
          disabled={page >= pageCount}
          onClick={() => onPageChange(page + 1)}
        >
          下一页
        </Button>
      </div>
    </div>
  )
}

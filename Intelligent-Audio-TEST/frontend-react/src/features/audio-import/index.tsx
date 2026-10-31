/**
 * 音频管理页（16_设备域.md §5；INT-505 可视稿）。
 * SectionPageLayout fixedContent + Title「音频管理」徽标「共 {n} 个」+ 页头动作区
 * （上传音频/批量从文件夹导入/URL 导入/批量更新标注/更多操作）+ 统计徽章行 + 视图切换
 * Tabs（列表/文件夹）+ 筛选工具栏（搜索+格式/音频类型/采样率/时长/标签 facet + 全局算法
 * chip）+ 列表视图 DataTable（§5.3）+ 文件夹视图左树右表（§5.5）+ 上传进度卡（§5.4）
 * + 批量浮条（§5.6）+ 分页 Portal（§3.9）。
 * 数据经 infrastructure/api/audios-api.ts（INT-645 切真实后端，client.ts 统一 fetch）。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Download, FolderOpen, List, MoreHorizontal, Plus, RefreshCw, Tags, Trash2, UploadCloud } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { PageFooterPortal } from '@/components/layout/components/page-footer'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { usePermissions } from '@/application/hooks/use-permissions'
import { downloadAudio, type AudioListResult } from '@/infrastructure/api/audios-api'
import {
  useAudioList,
  useAudioMutations,
  useAudioTags,
  useFolderTree,
} from '@/application/audio/useAudioList'
import {
  DEFAULT_PAGE_SIZE,
} from '@/features/audio-import/constants'
import { AudioStatsRow } from '@/features/audio-import/components/audio-stats-row'
import { AudioFilterToolbar } from '@/features/audio-import/components/audio-filter-toolbar'
import { AudioTable } from '@/features/audio-import/components/audio-table'
import { AudioFolderView } from '@/features/audio-import/components/audio-folder-view'
import { AudioBulkActions } from '@/features/audio-import/components/audio-bulk-actions'
import { UploadProgressCard } from '@/features/audio-import/components/upload-progress-card'
import { PaginationBar } from '@/features/audio-import/components/pagination-bar'
import { AudioUploadDialog } from '@/features/audio-import/components/modals/audio-upload-dialog'
import { AudioFolderImportDialog } from '@/features/audio-import/components/modals/audio-folder-import-dialog'
import { AudioUrlImportDialog } from '@/features/audio-import/components/modals/audio-url-import-dialog'
import { AudioBatchAnnotationDialog } from '@/features/audio-import/components/modals/audio-batch-annotation-dialog'
import { AudioPreviewDialog } from '@/features/audio-import/components/modals/audio-preview-dialog'
import { AudioMetadataDialog } from '@/features/audio-import/components/modals/audio-metadata-dialog'
import { AudioConvertDialog } from '@/features/audio-import/components/modals/audio-convert-dialog'
import { AudioFeatureAnalysisDialog } from '@/features/audio-import/components/modals/audio-feature-analysis-dialog'
import { AudioBatchTagsDialog } from '@/features/audio-import/components/modals/audio-batch-tags-dialog'
import { AudioBatchOperationDialog } from '@/features/audio-import/components/modals/audio-batch-operation-dialog'
import type { AudioAsset } from '@/domain/models/audio'
import type {
  AudioBulkDialogState,
  AudioListFilters,
  AudioRowDialogState,
  AudioViewMode,
} from '@/features/audio-import/types'

const DEFAULT_FILTERS: AudioListFilters = {
  search: '',
  format: null,
  audioType: null,
  sampleRate: null,
  duration: null,
  tags: [],
  tagMode: 'or',
  visibility: null,
}

/** 搜索防抖毫秒（§5.2 search debounce 500ms 口径） */

export function AudioImportPage() {
  const { hasPermission } = usePermissions()
  const canUpload = hasPermission('audio:upload')
  const canUpdate = hasPermission('audio:update')
  const canDelete = hasPermission('audio:delete')
  const canConvert = hasPermission('audio:convert')
  const canFolder = hasPermission('audio:folder')

  const [view, setView] = useState<AudioViewMode>('list')
  const [filters, setFilters] = useState<AudioListFilters>(DEFAULT_FILTERS)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc')
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())

  // 弹窗群
  const [uploadOpen, setUploadOpen] = useState(false)
  const [folderImportOpen, setFolderImportOpen] = useState(false)
  const [urlImportOpen, setUrlImportOpen] = useState(false)
  const [batchAnnotationOpen, setBatchAnnotationOpen] = useState(false)
  const [rowDialog, setRowDialog] = useState<AudioRowDialogState | null>(null)
  const [bulkDialog, setBulkDialog] = useState<AudioBulkDialogState | null>(null)
  const [bulkTagsOpen, setBulkTagsOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<AudioAsset | null>(null)
  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false)
  const [confirmPending, setConfirmPending] = useState(false)

  const audiosQuery = useAudioList({
    page,
    perPage: pageSize,
    search: filters.search,
    format: filters.format,
    audioType: filters.audioType,
    sampleRate: filters.sampleRate,
    duration: filters.duration,
    tags: filters.tags,
    tagMode: filters.tagMode,
    visibility: filters.visibility,
    // 标签 OR 模式与文件夹视图需要跨页完整行集（后端不表达 OR / 列表接口无 folder 过滤）
    allRows: view === 'folder' || (filters.tags.length > 0 && filters.tagMode === 'or'),
  })
  const tagsQuery = useAudioTags()
  const folderTreeQuery = useFolderTree()
  const { remove, batch, invalidate } = useAudioMutations()

  const tags = tagsQuery.data ?? []
  const folderTree = folderTreeQuery.data ?? []

  /* ───────── 服务端分页 / OR 标签客户端过滤 / 排序 ───────── */

  // 后端仅 AND 标签语义（GET tags 参数 422 / POST 仅 AND）；OR 标签置 allRows 拉全量行客户端过滤
  const tagsClientSide =
    filters.tags.length > 0 && filters.tagMode === 'or'
  const needAllRows = view === 'folder' || tagsClientSide

  // 列表失败时保留上一次成功加载的行（INT-1583：翻页/筛选失败不清空已有数据）
  // React Query 的 placeholderData 只覆盖 pending 态，查询失败后 data 变 undefined，
  // 故在此留一份「最近一次成功结果」快照供失败时回显。
  const lastGoodList = useRef<AudioListResult | null>(null)
  if (audiosQuery.data) lastGoodList.current = audiosQuery.data
  const listData = audiosQuery.data ?? lastGoodList.current ?? undefined

  // 服务端已做 scalar facet（+ AND 标签）过滤；OR 标签在此按全量行客户端过滤
  const displayRows = tagsClientSide
    ? (listData?.items ?? []).filter((row) =>
        filters.tags.some((tag) => row.tags.includes(tag))
      )
    : (listData?.items ?? [])

  // 排序：服务端分页按后端 created_at desc（列表排序钮隐藏）；allRows 模式才可客户端排序
  const sorted = useMemo(() => {
    if (!needAllRows) return displayRows
    const rows = [...displayRows]
    rows.sort((a, b) => {
      const diff =
        new Date(b.createdAt ?? 0).getTime() - new Date(a.createdAt ?? 0).getTime()
      return sortOrder === 'desc' ? diff : -diff
    })
    return rows
  }, [displayRows, needAllRows, sortOrder])

  const displayTotal = tagsClientSide
    ? sorted.length
    : (listData?.total ?? sorted.length)
  const pageCount = Math.max(1, Math.ceil(displayTotal / pageSize))
  const safePage = Math.min(page, pageCount)

  /* ───────── 列表失败（INT-1583） ───────── */

  // 失败不等于空库：表格显示错误态 / 保留旧数据 + 行内提示，标题计数不再显示 0
  const listError = audiosQuery.isError
  const lastErrorToastAt = useRef(0)

  // 翻页 / 筛选失败但仍有上次数据：toast 一次（首屏失败由表格错误态承担）
  useEffect(() => {
    if (!listError) return
    if (audiosQuery.errorUpdatedAt === lastErrorToastAt.current) return
    lastErrorToastAt.current = audiosQuery.errorUpdatedAt
    if (displayRows.length === 0) return
    toast.error('音频列表加载失败，已保留上一次加载的数据，请重试')
  }, [listError, audiosQuery.errorUpdatedAt, displayRows.length])

  // 越界兜底：筛选/删除后总页数收缩时把页码拉回。
  // 仅在查询成功时兜底——失败时 pageCount 会因 data 缺失回落成 1，若照旧拉回会把刚翻页的
  // 失败状态整个吞掉（用户点「下一页」毫无反应），见 INT-1583。
  useEffect(() => {
    if (!audiosQuery.isSuccess) return
    if (page > 0 && pageCount > 0 && page > pageCount) setPage(pageCount)
  }, [audiosQuery.isSuccess, page, pageCount])

  // 列表视图行：服务端分页时即当前页；OR 标签客户端过滤时按本地分页切片
  const listRows = useMemo(
    () =>
      tagsClientSide
        ? sorted.slice((safePage - 1) * pageSize, safePage * pageSize)
        : sorted,
    [tagsClientSide, sorted, safePage, pageSize]
  )

  const isFiltered =
    filters.search !== '' ||
    filters.format != null ||
    filters.audioType != null ||
    filters.sampleRate != null ||
    filters.duration != null ||
    filters.visibility != null ||
    filters.tags.length > 0

  /* ───────── 选择 ───────── */

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  /** 全选/取消当前行集（列表视图传 pageRows、文件夹视图传其自身 folder pageRows，各表头态与真实选择一致） */
  const toggleSelectAll = (ids: number[]) => {
    setSelectedIds((prev) => {
      if (ids.length === 0) return prev
      const allSelected = ids.every((id) => prev.has(id))
      if (allSelected) {
        const next = new Set(prev)
        ids.forEach((id) => next.delete(id))
        return next
      }
      const next = new Set(prev)
      ids.forEach((id) => next.add(id))
      return next
    })
  }

  /* ───────── 行操作 ───────── */

  const currentRowAudio = useMemo(() => {
    if (!rowDialog) return null
    // 列表页行集=当前页、文件夹视图行集=全量行（allRows），弹窗音频都能在行集内找到
    return sorted.find((a) => a.id === rowDialog.audioId) ?? null
  }, [rowDialog, sorted])

  const handleDownload = async (audio: AudioAsset) => {
    // §5.3.1：二次取流（后端 stream 返 JSON 预签名 URL，前端再取字节流）
    try {
      const blob = await downloadAudio(audio.id)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = audio.name
      anchor.click()
      URL.revokeObjectURL(url)
      toast.success('音频已开始下载')
    } catch {
      toast.error('下载失败，请重试')
    }
  }

  const handleExport = async () => {
    if (selectedIds.size === 0) return
    // §5.6：batch-action export，解析 zip_base64→Blob 下载（INT 修正现状 blob 直消费缺陷 §11-14）
    try {
      const result = await batch.mutateAsync({
        action: 'export',
        ids: [...selectedIds],
      })
      if (result.zipBase64) {
        const binary = atob(result.zipBase64)
        const bytes = new Uint8Array(binary.length)
        for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
        const blob = new Blob([bytes], { type: 'application/zip' })
        const url = URL.createObjectURL(blob)
        const anchor = document.createElement('a')
        anchor.href = url
        anchor.download = result.filename ?? `audios_export_${Date.now()}.zip`
        anchor.click()
        URL.revokeObjectURL(url)
      }
      toast.success(`已导出 ${selectedIds.size} 个音频`)
    } catch {
      toast.error('导出失败，请重试')
    }
  }

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return
    setConfirmPending(true)
    try {
      const result = await remove.mutateAsync(deleteTarget.id)
      if (result.success) {
        toast.success('音频文件已删除')
      } else {
        toast.error(result.message ?? '删除失败，请重试')
      }
      setDeleteTarget(null)
    } catch {
      toast.error('删除失败，请重试')
    } finally {
      setConfirmPending(false)
    }
  }

  const handleConfirmBatchDelete = async () => {
    setConfirmPending(true)
    try {
      const result = await batch.mutateAsync({ action: 'delete', ids: [...selectedIds] })
      toast.success(
        result.message ??
          `批量删除完成：成功 ${result.successCount}，跳过 ${result.total - result.successCount}`
      )
      setSelectedIds(new Set())
      setBatchDeleteOpen(false)
    } catch {
      toast.error('批量删除失败，请重试')
    } finally {
      setConfirmPending(false)
    }
  }

  /* ───────── 页面装配（§5.1 骨架） ───────── */

  const audioTableCallbacks = {
    onToggleSelect: toggleSelect,
    onToggleSelectAll: toggleSelectAll,
    canUpdate,
    canConvert,
    canDelete,
    sortOrder,
    onSortChange: () => setSortOrder((prev) => (prev === 'desc' ? 'asc' : 'desc')),
    onEmptyUpload: () => setUploadOpen(true),
    onPreview: (audio: AudioAsset) => setRowDialog({ kind: 'preview', audioId: audio.id }),
    onMetadata: (audio: AudioAsset) => setRowDialog({ kind: 'metadata', audioId: audio.id }),
    onDownload: handleDownload,
    onConvert: (audio: AudioAsset) => setRowDialog({ kind: 'convert', audioId: audio.id }),
    onFeatureAnalysis: (audio: AudioAsset) =>
      setRowDialog({ kind: 'feature-analysis', audioId: audio.id }),
    onDelete: (audio: AudioAsset) => setDeleteTarget(audio),
  }

  return (
    <>
      <SectionPageLayout fixedContent>
        <SectionPageLayout.Title>
          <span className='flex flex-wrap items-center gap-2'>
            音频管理
            <Badge variant='outline' className='font-normal tabular-nums'>
              {listError ? '共 — 个' : `共 ${displayTotal} 个`}
            </Badge>
          </span>
        </SectionPageLayout.Title>

        <SectionPageLayout.Actions>
          <div className='flex flex-wrap items-center gap-2'>
            {canUpload && (
              <Button size='sm' className='gap-1.5' onClick={() => setUploadOpen(true)}>
                <Plus aria-hidden='true' className='size-3.5' />
                上传音频
              </Button>
            )}
            {canUpload && (
              <Button
                variant='outline'
                size='sm'
                className='gap-1.5'
                onClick={() => setFolderImportOpen(true)}
              >
                <FolderOpen aria-hidden='true' className='size-3.5' />
                批量从文件夹导入
              </Button>
            )}
            {canUpload && (
              <Button
                variant='outline'
                size='sm'
                className='gap-1.5'
                onClick={() => setUrlImportOpen(true)}
              >
                <UploadCloud aria-hidden='true' className='size-3.5' />
                URL 导入
              </Button>
            )}
            {canUpdate && (
              <Button
                variant='outline'
                size='sm'
                className='gap-1.5'
                onClick={() => setBatchAnnotationOpen(true)}
              >
                <Tags aria-hidden='true' className='size-3.5' />
                批量更新标注
              </Button>
            )}
            <DropdownMenu>
              <DropdownMenuTrigger
                render={<Button variant='outline' size='icon-sm' aria-label='更多操作' />}
              >
                <MoreHorizontal aria-hidden='true' />
              </DropdownMenuTrigger>
              <DropdownMenuContent align='end' className='w-44'>
                {canDelete && (
                  <DropdownMenuItem
                    disabled={selectedIds.size === 0}
                    onClick={() => setBatchDeleteOpen(true)}
                  >
                    <Trash2 aria-hidden='true' />
                    批量删除
                  </DropdownMenuItem>
                )}
                {canUpdate && (
                  <DropdownMenuItem
                    disabled={selectedIds.size === 0}
                    onClick={handleExport}
                  >
                    <Download aria-hidden='true' />
                    批量导出
                  </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => {
                    invalidate()
                    toast.success('列表已刷新')
                  }}
                >
                  <RefreshCw aria-hidden='true' />
                  刷新列表
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </SectionPageLayout.Actions>

        <SectionPageLayout.Content>
          <div className='flex h-full min-h-0 flex-col gap-3'>
            <UploadProgressCard />

            {/* 首屏失败且无历史统计时不摆一排永久骨架（错误态已表明加载失败，INT-1583） */}
            {(!listError || listData != null) && (
              <AudioStatsRow stats={listData?.stats} />
            )}

            <Tabs value={view} onValueChange={(value) => setView(value as AudioViewMode)}>
              <TabsList variant='line' className='w-fit'>
                <TabsTrigger value='list' className='gap-1.5'>
                  <List aria-hidden='true' className='size-3.5' />
                  列表视图
                </TabsTrigger>
                {canFolder && (
                  <TabsTrigger value='folder' className='gap-1.5'>
                    <FolderOpen aria-hidden='true' className='size-3.5' />
                    文件夹视图
                  </TabsTrigger>
                )}
              </TabsList>
            </Tabs>

            <AudioFilterToolbar
              filters={filters}
              tags={tags}
              onChange={(next) => {
                setFilters(next)
                setPage(1)
              }}
              onReset={() => {
                setFilters(DEFAULT_FILTERS)
                setPage(1)
              }}
              isFiltered={isFiltered}
            />

            {view === 'list' ? (
              <div className='min-h-0 flex-1 overflow-y-auto'>
                <AudioTable
                  rows={listRows}
                  loading={audiosQuery.isLoading}
                  isError={listError}
                  onRetry={() => void audiosQuery.refetch()}
                  total={displayTotal}
                  searchKeyword={filters.search}
                  selectedIds={selectedIds}
                  sortable={needAllRows}
                  {...audioTableCallbacks}
                />
              </div>
            ) : (
              <div className='min-h-0 flex-1'>
                <AudioFolderView
                  tree={folderTree}
                  rows={sorted}
                  loading={audiosQuery.isLoading}
                  isError={listError}
                  onRetry={() => void audiosQuery.refetch()}
                  selectedIds={selectedIds}
                  canUpload={canUpload}
                  onFolderImport={() => setFolderImportOpen(true)}
                  {...audioTableCallbacks}
                />
              </div>
            )}

            {/* 批量浮条（§5.6） */}
            <AudioBulkActions
              count={selectedIds.size}
              canDelete={canDelete}
              canUpdate={canUpdate}
              onClear={() => setSelectedIds(new Set())}
              onDelete={() => setBatchDeleteOpen(true)}
              onExport={handleExport}
              onOpenTagsDialog={() => setBulkTagsOpen(true)}
              onOpenBulkDialog={(state) => setBulkDialog(state)}
            />

            {/* 失败且无行时分页无意义（不显示「共 0 条」误导为库空，INT-1583） */}
            {view === 'list' && !(listError && displayRows.length === 0) && (
              <PageFooterPortal>
                <PaginationBar
                  page={safePage}
                  pageCount={pageCount}
                  pageSize={pageSize}
                  total={displayTotal}
                  onPageChange={setPage}
                  onPageSizeChange={(size) => {
                    setPageSize(size)
                    setPage(1)
                  }}
                />
              </PageFooterPortal>
            )}
          </div>
        </SectionPageLayout.Content>
      </SectionPageLayout>

      {/* 弹窗群（§6，Context Provider 挂页级） */}
      <AudioUploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
      <AudioFolderImportDialog
        open={folderImportOpen}
        onOpenChange={setFolderImportOpen}
      />
      <AudioUrlImportDialog open={urlImportOpen} onOpenChange={setUrlImportOpen} />
      <AudioBatchAnnotationDialog
        open={batchAnnotationOpen}
        onOpenChange={setBatchAnnotationOpen}
      />

      <AudioPreviewDialog
        open={rowDialog?.kind === 'preview'}
        onOpenChange={(open) => !open && setRowDialog(null)}
        audio={currentRowAudio}
      />
      <AudioMetadataDialog
        open={rowDialog?.kind === 'metadata'}
        onOpenChange={(open) => !open && setRowDialog(null)}
        audio={currentRowAudio}
      />
      <AudioConvertDialog
        open={rowDialog?.kind === 'convert'}
        onOpenChange={(open) => !open && setRowDialog(null)}
        audio={currentRowAudio}
      />
      <AudioFeatureAnalysisDialog
        open={rowDialog?.kind === 'feature-analysis'}
        onOpenChange={(open) => !open && setRowDialog(null)}
        audio={currentRowAudio}
      />

      <AudioBatchTagsDialog
        open={bulkTagsOpen}
        onOpenChange={setBulkTagsOpen}
        count={selectedIds.size}
        ids={[...selectedIds]}
      />
      <AudioBatchOperationDialog
        state={bulkDialog}
        onOpenChange={(open) => !open && setBulkDialog(null)}
        count={selectedIds.size}
        ids={[...selectedIds]}
      />

      <ConfirmDialog
        open={deleteTarget != null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title='删除音频'
        desc={
          deleteTarget
            ? `确定要删除音频「${deleteTarget.name}」吗？此操作不可撤销。`
            : ''
        }
        destructive
        confirmText='删除'
        isLoading={confirmPending}
        handleConfirm={handleConfirmDelete}
      />

      <ConfirmDialog
        open={batchDeleteOpen}
        onOpenChange={setBatchDeleteOpen}
        title='批量删除音频'
        desc={`确定删除选中的 ${selectedIds.size} 个音频吗？被测试用例/任务引用的音频将跳过。此操作不可撤销。`}
        destructive
        confirmText='批量删除'
        isLoading={confirmPending}
        handleConfirm={handleConfirmBatchDelete}
      />
    </>
  )
}

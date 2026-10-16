/**
 * 音频管理页（16_设备域.md §5；INT-505 可视稿）。
 * SectionPageLayout fixedContent + Title「音频管理」徽标「共 {n} 个」+ 页头动作区
 * （上传音频/批量从文件夹导入/URL 导入/批量更新标注/更多操作）+ 统计徽章行 + 视图切换
 * Tabs（列表/文件夹）+ 筛选工具栏（搜索+格式/音频类型/采样率/时长/标签 facet + 全局算法
 * chip）+ 列表视图 DataTable（§5.3）+ 文件夹视图左树右表（§5.5）+ 上传进度卡（§5.4）
 * + 批量浮条（§5.6）+ 分页 Portal（§3.9）。
 * mock 数据对齐 api_gateway/schemas/audio.py（AudioItem/AudioListStats）；不接后端。
 */
import { useMemo, useState } from 'react'
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
import { AudioPlaybackHistoryDialog } from '@/features/audio-import/components/modals/audio-playback-history-dialog'
import { AudioBatchTagsDialog } from '@/features/audio-import/components/modals/audio-batch-tags-dialog'
import { AudioBatchOperationDialog } from '@/features/audio-import/components/modals/audio-batch-operation-dialog'
import { durationBucket } from '@/features/audio-import/lib/format'
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
}

/** 搜索防抖毫秒（§5.2 search debounce 500ms 口径） */

export function AudioImportPage() {
  const { hasPermission } = usePermissions()
  const canUpload = hasPermission('audio:upload')
  const canUpdate = hasPermission('audio:update')
  const canDelete = hasPermission('audio:delete')
  const canConvert = hasPermission('audio:convert')
  const canFolder = hasPermission('audio:folder')

  const audiosQuery = useAudioList()
  const tagsQuery = useAudioTags()
  const folderTreeQuery = useFolderTree()
  const { remove, batch, invalidate } = useAudioMutations()

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

  const audios = audiosQuery.data?.items ?? []
  const tags = tagsQuery.data ?? []
  const folderTree = folderTreeQuery.data ?? []

  /* ───────── 过滤 / 排序 / 分页 ───────── */

  const filtered = useMemo(() => {
    let rows = audios
    const keyword = filters.search.trim().toLowerCase()
    if (keyword) {
      rows = rows.filter(
        (row) =>
          row.name.toLowerCase().includes(keyword) ||
          (row.asrText ?? '').toLowerCase().includes(keyword)
      )
    }
    if (filters.format) rows = rows.filter((row) => row.format === filters.format)
    if (filters.audioType) rows = rows.filter((row) => row.audioType === filters.audioType)
    if (filters.sampleRate) {
      rows = rows.filter(
        (row) => row.sampleRate != null && String(row.sampleRate) === filters.sampleRate
      )
    }
    if (filters.duration) {
      rows = rows.filter((row) => durationBucket(row.duration) === filters.duration)
    }
    if (filters.tags.length > 0) {
      rows = rows.filter((row) =>
        filters.tagMode === 'or'
          ? filters.tags.some((tag) => row.tags.includes(tag))
          : filters.tags.every((tag) => row.tags.includes(tag))
      )
    }
    return rows
  }, [audios, filters])

  const sorted = useMemo(() => {
    const rows = [...filtered]
    rows.sort((a, b) => {
      const diff = new Date(b.createdAt ?? 0).getTime() - new Date(a.createdAt ?? 0).getTime()
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

  const isFiltered =
    filters.search !== '' ||
    filters.format != null ||
    filters.audioType != null ||
    filters.sampleRate != null ||
    filters.duration != null ||
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

  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      if (pageRows.length > 0 && prev.size === pageRows.length) return new Set()
      return new Set(pageRows.map((row) => row.id))
    })
  }

  /* ───────── 行操作 ───────── */

  const currentRowAudio = useMemo(() => {
    if (!rowDialog) return null
    return audios.find((a) => a.id === rowDialog.audioId) ?? null
  }, [rowDialog, audios])

  const handleDownload = (audio: AudioAsset) => {
    // §5.3.1：二次取流（后端 stream 返 JSON 预签名 URL，前端再取字节流）——mock 直接 Blob
    const blob = new Blob([`mock audio content: ${audio.name}`], {
      type: 'application/octet-stream',
    })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = audio.name
    anchor.click()
    URL.revokeObjectURL(url)
    toast.success('音频已开始下载')
  }

  const handleExport = () => {
    // §5.6：batch-action export，解析 zip_base64→Blob 下载（修正现状 blob 直消费缺陷 §11-14）
    const rows = audios.filter((a) => selectedIds.has(a.id))
    const blob = new Blob([JSON.stringify(rows, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    const date = new Date().toISOString().slice(0, 10)
    anchor.href = url
    anchor.download = `audios_${date}.json`
    anchor.click()
    URL.revokeObjectURL(url)
    void batch.mutateAsync({ action: 'export', ids: [...selectedIds] })
    toast.success(`已导出 ${selectedIds.size} 个音频`)
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
    onPlaybackHistory: (audio: AudioAsset) =>
      setRowDialog({ kind: 'playback-history', audioId: audio.id }),
    onDelete: (audio: AudioAsset) => setDeleteTarget(audio),
  }

  return (
    <>
      <SectionPageLayout fixedContent>
        <SectionPageLayout.Title>
          <span className='flex flex-wrap items-center gap-2'>
            音频管理
            <Badge variant='outline' className='font-normal tabular-nums'>
              共 {audiosQuery.data?.stats.totalFiles ?? audios.length} 个
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
                <DropdownMenuItem
                  disabled={selectedIds.size === 0}
                  onClick={() => setBatchDeleteOpen(true)}
                >
                  <Trash2 aria-hidden='true' />
                  批量删除
                </DropdownMenuItem>
                <DropdownMenuItem
                  disabled={selectedIds.size === 0}
                  onClick={handleExport}
                >
                  <Download aria-hidden='true' />
                  批量导出
                </DropdownMenuItem>
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

            <AudioStatsRow stats={audiosQuery.data?.stats} />

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
                  rows={pageRows}
                  loading={audiosQuery.isLoading}
                  total={sorted.length}
                  searchKeyword={filters.search}
                  selectedIds={selectedIds}
                  {...audioTableCallbacks}
                />
              </div>
            ) : (
              <div className='min-h-0 flex-1'>
                <AudioFolderView
                  tree={folderTree}
                  rows={sorted}
                  loading={audiosQuery.isLoading}
                  selectedIds={selectedIds}
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
              onOpenBulkDialog={(state) => setBulkDialog(state)}
            />

            {view === 'list' && (
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
      <AudioPlaybackHistoryDialog
        open={rowDialog?.kind === 'playback-history'}
        onOpenChange={(open) => !open && setRowDialog(null)}
        audio={currentRowAudio}
      />

      <AudioBatchTagsDialog
        open={bulkTagsOpen}
        onOpenChange={setBulkTagsOpen}
        count={selectedIds.size}
      />
      <AudioBatchOperationDialog
        state={bulkDialog}
        onOpenChange={(open) => !open && setBulkDialog(null)}
        count={selectedIds.size}
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

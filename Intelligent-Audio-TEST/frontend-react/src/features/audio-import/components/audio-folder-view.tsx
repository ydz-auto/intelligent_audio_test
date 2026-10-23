/**
 * 文件夹视图（§5.5 左树右表）：左 Collapsible 树（节点=ChevronRight 展开 + Folder/FolderOpen
 * 图标 + 名称 + 计数 Badge + 文件数），右表复用 §5.3 列定义（folder 参数过滤）。
 * 文件夹卡头部「上传音频/批量从文件夹导入」入口钮（→全局 pendingAction）。
 */
import { ChevronRight, Folder, FolderOpen, Upload } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import type { AudioAsset, AudioFolderNode } from '@/domain/models/audio'
import { AudioTable } from '@/features/audio-import/components/audio-table'
import { PaginationBar } from '@/features/audio-import/components/pagination-bar'
import { DEFAULT_PAGE_SIZE } from '@/features/audio-import/constants'

export type AudioFolderViewProps = {
  tree: AudioFolderNode[]
  /** 已按工具栏筛选 + 排序的全量行（未按文件夹过滤） */
  rows: AudioAsset[]
  loading: boolean
  /** 列表查询失败（INT-1583）：右表显示错误态 / 保留旧数据提示 */
  isError?: boolean
  /** 查询失败重试（refetch） */
  onRetry?: () => void
  selectedIds: Set<number>
  onToggleSelect: (id: number) => void
  /** 全选当前文件夹表格行集（文件夹视图按自身 pageRows 计算，而非列表视图行） */
  onToggleSelectAll: (ids: number[]) => void
  canUpload: boolean
  /** 「批量从文件夹导入」入口（§5.5 文件夹卡头部两钮之一；页头同款弹窗） */
  onFolderImport: () => void
  canUpdate: boolean
  canConvert: boolean
  canDelete: boolean
  sortOrder: 'asc' | 'desc'
  onSortChange: () => void
  onEmptyUpload: () => void
  onPreview: (audio: AudioAsset) => void
  onMetadata: (audio: AudioAsset) => void
  onDownload: (audio: AudioAsset) => void
  onConvert: (audio: AudioAsset) => void
  onFeatureAnalysis: (audio: AudioAsset) => void
  onPlaybackHistory: (audio: AudioAsset) => void
  onDelete: (audio: AudioAsset) => void
}

function FolderNode({
  node,
  depth,
  selectedPath,
  onSelect,
}: {
  node: AudioFolderNode
  depth: number
  selectedPath: string | null
  onSelect: (path: string) => void
}) {
  const [open, setOpen] = useState(depth === 1)
  const hasChildren = node.children.length > 0
  const isSelected = node.path === selectedPath

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div
        className={cn(
          'hover:bg-muted/40 flex items-center gap-1.5 rounded-md py-1.5 pe-2 text-sm transition-colors',
          isSelected && 'bg-primary/[0.06] dark:bg-primary/10'
        )}
        style={{ paddingInlineStart: `${depth * 12 + 4}px` }}
      >
        {hasChildren ? (
          <CollapsibleTrigger
            render={
              <button
                type='button'
                aria-label={`展开文件夹 ${node.name}`}
                aria-expanded={open}
                className='text-muted-foreground hover:text-foreground shrink-0 transition-colors'
              />
            }
          >
            <ChevronRight
              aria-hidden='true'
              className={cn('size-3.5 transition-transform', open && 'rotate-90')}
            />
          </CollapsibleTrigger>
        ) : (
          <span aria-hidden='true' className='size-3.5 shrink-0' />
        )}
        <button
          type='button'
          onClick={() => onSelect(node.path)}
          className='flex min-w-0 flex-1 items-center gap-1.5 text-start'
        >
          {isSelected ? (
            <FolderOpen aria-hidden='true' className='text-primary size-4 shrink-0' />
          ) : (
            <Folder aria-hidden='true' className='text-muted-foreground size-4 shrink-0' />
          )}
          <span className='min-w-0 flex-1 truncate font-medium'>{node.name}</span>
          {node.count > 0 && (
            <Badge variant='secondary' className='rounded-sm px-1 font-normal'>
              {node.count}
            </Badge>
          )}
          <span className='text-muted-foreground shrink-0 font-mono text-xs tabular-nums'>
            {node.fileCount}
          </span>
        </button>
      </div>
      {hasChildren && (
        <CollapsibleContent className='mt-0.5'>
          <div className='space-y-0.5'>
            {node.children.map((child) => (
              <FolderNode
                key={child.path}
                node={child}
                depth={depth + 1}
                selectedPath={selectedPath}
                onSelect={onSelect}
              />
            ))}
          </div>
        </CollapsibleContent>
      )}
    </Collapsible>
  )
}

export function AudioFolderView(props: AudioFolderViewProps) {
  const [selectedPath, setSelectedPath] = useState<string | null>(
    props.tree[0]?.path ?? null
  )
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)

  const folderRows = useMemo(() => {
    if (!selectedPath) return []
    return props.rows.filter(
      (audio) => audio.filePath?.startsWith(selectedPath) ?? false
    )
  }, [props.rows, selectedPath])

  const pageCount = Math.max(1, Math.ceil(folderRows.length / pageSize))
  const safePage = Math.min(page, pageCount)
  const pageRows = folderRows.slice(
    (safePage - 1) * pageSize,
    safePage * pageSize
  )

  return (
    <div className='bg-card ring-foreground/10 grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-hidden rounded-xl ring-1 md:grid-cols-[240px_minmax(0,1fr)]'>
      {/* 左树 */}
      <aside className='border-border/60 min-h-0 border-b p-2 md:border-r md:border-b-0'>
        <div className='text-muted-foreground mb-1 px-1.5 text-xs font-medium'>
          文件夹
        </div>
        <div className='max-h-64 space-y-0.5 overflow-y-auto md:max-h-none'>
          {props.tree.map((node) => (
            <FolderNode
              key={node.path}
              node={node}
              depth={1}
              selectedPath={selectedPath}
              onSelect={(path) => {
                setSelectedPath(path)
                setPage(1)
              }}
            />
          ))}
        </div>
      </aside>

      {/* 右表 */}
      <div className='flex min-h-0 min-w-0 flex-col gap-2 p-2 sm:p-3'>
        <div className='flex flex-wrap items-center gap-2'>
          <div className='text-muted-foreground min-w-0 flex-1 truncate text-xs'>
            当前文件夹：
            <span className='text-foreground font-mono'>{selectedPath ?? '—'}</span>
          </div>
          {props.canUpload && (
            <Button variant='outline' size='sm' className='h-7 gap-1.5 px-2.5' onClick={props.onEmptyUpload}>
              <Upload aria-hidden='true' className='size-3.5' />
              上传音频
            </Button>
          )}
          {props.canUpload && (
            <Button variant='outline' size='sm' className='h-7 gap-1.5 px-2.5' onClick={props.onFolderImport}>
              <FolderOpen aria-hidden='true' className='size-3.5' />
              批量从文件夹导入
            </Button>
          )}
        </div>
        <div className='min-h-0 flex-1 overflow-y-auto'>
          <AudioTable
            rows={pageRows}
            loading={props.loading}
            isError={props.isError}
            onRetry={props.onRetry}
            total={folderRows.length}
            searchKeyword=''
            selectedIds={props.selectedIds}
            onToggleSelect={props.onToggleSelect}
            onToggleSelectAll={props.onToggleSelectAll}
            canUpdate={props.canUpdate}
            canConvert={props.canConvert}
            canDelete={props.canDelete}
            sortOrder={props.sortOrder}
            onSortChange={props.onSortChange}
            onEmptyUpload={props.onEmptyUpload}
            onPreview={props.onPreview}
            onMetadata={props.onMetadata}
            onDownload={props.onDownload}
            onConvert={props.onConvert}
            onFeatureAnalysis={props.onFeatureAnalysis}
            onPlaybackHistory={props.onPlaybackHistory}
            onDelete={props.onDelete}
          />
        </div>
        {/* 失败且无行时分页无意义（不显示「共 0 条」误导为库空，INT-1583） */}
        {!(props.isError && folderRows.length === 0) && (
          <PaginationBar
            page={safePage}
            pageCount={pageCount}
            pageSize={pageSize}
            total={folderRows.length}
            onPageChange={setPage}
            onPageSizeChange={(size) => {
              setPageSize(size)
              setPage(1)
            }}
          />
        )}
      </div>
    </div>
  )
}

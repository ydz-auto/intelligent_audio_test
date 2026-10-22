/**
 * 音频列表数据表（§5.3；DataTablePage 对位——列=勾选/ID/文件名/格式/大小/时长/
 * 音频类型/源语言/标签/创建时间/操作）。桌面表格 + 移动端卡片同源列定义（§2.1 口径）。
 */
import { Box, ChevronDown, ChevronUp } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { AudioAsset } from '@/domain/models/audio'
import { AudioTypeBadge } from '@/features/audio-import/components/audio-type-badge'
import { AudioRowActions } from '@/features/audio-import/components/audio-row-actions'
import {
  formatDateTime,
  formatDuration,
  formatFileSize,
} from '@/features/audio-import/lib/format'

export type AudioTableProps = {
  rows: AudioAsset[]
  loading: boolean
  total: number
  searchKeyword: string
  selectedIds: Set<number>
  onToggleSelect: (id: number) => void
  /** 全选当前页行集（由调用方传入当前表格的行 id，列表/文件夹视图各自计算） */
  onToggleSelectAll: (ids: number[]) => void
  canUpdate: boolean
  canConvert: boolean
  canDelete: boolean
  sortOrder: 'asc' | 'desc'
  onSortChange: () => void
  /** 是否可客户端排序（列表服务端分页时后端仅 created_at desc，排序钮隐藏） */
  sortable?: boolean
  onEmptyUpload: () => void
  onPreview: (audio: AudioAsset) => void
  onMetadata: (audio: AudioAsset) => void
  onDownload: (audio: AudioAsset) => void
  onConvert: (audio: AudioAsset) => void
  onFeatureAnalysis: (audio: AudioAsset) => void
  onPlaybackHistory: (audio: AudioAsset) => void
  onDelete: (audio: AudioAsset) => void
}

/** 标签列（§5.3 BadgeListCell 语义：最多 2 枚 + 「+N」tooltip 全量） */
function TagsCell({ tags }: { tags: string[] }) {
  if (tags.length === 0) return <span className='text-muted-foreground'>—</span>
  const visible = tags.slice(0, 2)
  const hidden = tags.slice(2)
  return (
    <div className='flex flex-wrap items-center gap-1'>
      {visible.map((tag) => (
        <Badge key={tag} variant='secondary' className='rounded-md px-1.5 font-normal'>
          {tag}
        </Badge>
      ))}
      {hidden.length > 0 && (
        <Tooltip>
          <TooltipTrigger
            render={<Badge variant='secondary' className='rounded-md px-1.5' tabIndex={0} />}
          >
            +{hidden.length}
          </TooltipTrigger>
          <TooltipContent className='max-w-64'>
            <div className='flex flex-wrap gap-1'>
              {hidden.map((tag) => (
                <Badge key={tag} variant='secondary' className='rounded-md px-1.5 font-normal'>
                  {tag}
                </Badge>
              ))}
            </div>
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  )
}

export function AudioTable(props: AudioTableProps) {
  const isEmpty = !props.loading && props.rows.length === 0
  // 当前页全部行均被选中才视为「全选」（跨页选择不影响本页表头态）
  const allSelected =
    !isEmpty &&
    props.rows.length > 0 &&
    props.rows.every((row) => props.selectedIds.has(row.id))

  if (props.loading) {
    return (
      <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
        <Skeleton className='h-10 w-full rounded-none border-b' />
        {Array.from({ length: Math.min(props.total || 8, 10) }).map((_, i) => (
          <Skeleton key={i} className='h-12 w-full rounded-none border-b' />
        ))}
      </div>
    )
  }

  if (isEmpty) {
    return (
      <div className='bg-card ring-foreground/10 rounded-xl ring-1'>
        <Empty className='h-80'>
          <EmptyMedia variant='icon'>
            <Box aria-hidden='true' className='size-4' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>
              {props.searchKeyword ? '未找到匹配的音频' : '暂无音频文件'}
            </EmptyTitle>
            <EmptyDescription>
              {props.searchKeyword
                ? '换个关键词或清除筛选条件试试'
                : '点击「上传音频」导入首批音频，或调整筛选条件'}
            </EmptyDescription>
          </EmptyHeader>
          {!props.searchKeyword && (
            <EmptyContent>
              <Button variant='outline' size='sm' onClick={props.onEmptyUpload}>
                <Box aria-hidden='true' className='size-3.5' />
                上传音频
              </Button>
            </EmptyContent>
          )}
        </Empty>
      </div>
    )
  }

  return (
    <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
      <div className='overflow-x-auto'>
        <table className='w-full min-w-[900px] text-[13px]'>
          <thead>
            <tr className='bg-[var(--table-header)] text-xs'>
              <th className='w-11 px-2.5 py-2'>
                <span className='flex items-center justify-center'>
                  <Checkbox
                    aria-label='全选当前页'
                    checked={allSelected}
                    onCheckedChange={() => props.onToggleSelectAll(props.rows.map((row) => row.id))}
                  />
                </span>
              </th>
              <th className='px-3 py-2 text-left font-medium'>ID</th>
              <th className='px-3 py-2 text-left font-medium'>文件名</th>
              <th className='px-3 py-2 text-left font-medium'>格式</th>
              <th className='px-3 py-2 text-right font-medium'>大小</th>
              <th className='px-3 py-2 text-right font-medium'>时长</th>
              <th className='px-3 py-2 text-left font-medium'>音频类型</th>
              <th className='px-3 py-2 text-left font-medium'>源语言</th>
              <th className='px-3 py-2 text-left font-medium'>标签</th>
              <th className='px-3 py-2 text-left font-medium'>
                {props.sortable === false ? (
                  <span>创建时间</span>
                ) : (
                  <button
                    type='button'
                    onClick={props.onSortChange}
                    className='hover:text-foreground inline-flex items-center gap-1 transition-colors'
                  >
                    创建时间
                    {props.sortOrder === 'desc' ? (
                      <ChevronDown aria-hidden='true' className='size-3' />
                    ) : (
                      <ChevronUp aria-hidden='true' className='size-3' />
                    )}
                  </button>
                )}
              </th>
              <th className='w-14 px-3 py-2 text-right font-medium'>操作</th>
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row) => (
              <tr
                key={row.id}
                className={cn(
                  'hover:bg-muted/40 border-border/50 border-b last:border-b-0',
                  props.selectedIds.has(row.id) && 'bg-primary/[0.04] dark:bg-primary/10'
                )}
              >
                <td className='px-2.5 py-2'>
                  <span className='flex items-center justify-center'>
                    <Checkbox
                      aria-label={`选择音频 ${row.name}`}
                      checked={props.selectedIds.has(row.id)}
                      onCheckedChange={() => props.onToggleSelect(row.id)}
                    />
                  </span>
                </td>
                <td className='px-3 py-2'>
                  <span className='font-mono text-xs text-muted-foreground tabular-nums'>
                    #{row.id}
                  </span>
                </td>
                <td className='max-w-52 px-3 py-2'>
                  <span className='min-w-0 block truncate font-medium' title={row.name}>
                    {row.name}
                  </span>
                  {row.originalFilename && row.originalFilename !== row.name && (
                    <span className='text-muted-foreground min-w-0 block truncate text-xs'>
                      {row.originalFilename}
                    </span>
                  )}
                </td>
                <td className='px-3 py-2'>
                  {row.format ? (
                    <Badge variant='outline' className='rounded-md px-1.5 font-normal'>
                      {(row.format ?? '').toUpperCase()}
                    </Badge>
                  ) : (
                    <span className='text-muted-foreground'>—</span>
                  )}
                </td>
                <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                  {formatFileSize(row.size)}
                </td>
                <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                  {formatDuration(row.duration)}
                </td>
                <td className='px-3 py-2'>
                  <AudioTypeBadge type={row.audioType} />
                </td>
                <td className='px-3 py-2'>
                  {row.sourceLanguage ? (
                    <span className='text-xs'>{row.sourceLanguage}</span>
                  ) : (
                    <span className='text-muted-foreground'>—</span>
                  )}
                </td>
                <td className='px-3 py-2'>
                  <TagsCell tags={row.tags} />
                </td>
                <td className='px-3 py-2 font-mono text-xs tabular-nums'>
                  {formatDateTime(row.createdAt)}
                </td>
                <td className='px-3 py-2'>
                  <div className='flex items-center justify-end gap-0.5'>
                    <AudioRowActions
                      audio={row}
                      canUpdate={props.canUpdate}
                      canConvert={props.canConvert}
                      canDelete={props.canDelete}
                      onPreview={() => props.onPreview(row)}
                      onMetadata={() => props.onMetadata(row)}
                      onDownload={() => props.onDownload(row)}
                      onConvert={() => props.onConvert(row)}
                      onFeatureAnalysis={() => props.onFeatureAnalysis(row)}
                      onPlaybackHistory={() => props.onPlaybackHistory(row)}
                      onDelete={() => props.onDelete(row)}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

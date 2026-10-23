/**
 * 播放设备列表数据表（16_设备域.md §3.5；DataTablePage 对位）。
 * 列：☑选择/ID/名称(+描述)/状态/设备类型/所属实验室/支持的格式/系统唯一标识/支持的通道数/
 * 采样率/声压映射/更新时间/操作。
 * INT-381 补口：支持的格式/支持的通道数列（后端 schema 未覆盖 mock 先行，§11-23）；
 * INT-487：所属实验室列 mock 先行；「测试中」占用态同 §3.4。
 * 离线行 DISABLED_ROW + 行菜单禁用（§3.5 注）。
 */
import { AudioLines, Box, Headphones } from 'lucide-react'

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
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import { PLAYBACK_DEVICE_TYPE_META } from '@/domain/models/playbackDevice'
import { DeviceStatusBadge } from '@/features/devices/components/device-status-badge'
import { DeviceRowActions } from '@/features/devices/components/device-row-actions'

export interface PlaybackDeviceTableProps {
  rows: PlaybackDevice[]
  loading: boolean
  total: number
  searchKeyword: string
  selectedIds: Set<number>
  batchMode: boolean
  sortOrder: 'asc' | 'desc'
  onSortChange: () => void
  onToggleSelect: (id: number) => void
  onToggleSelectAll: () => void
  canRead: boolean
  canUpdate: boolean
  canDelete: boolean
  canControl: boolean
  canHealth: boolean
  onDetail: (device: PlaybackDevice) => void
  onEdit: (device: PlaybackDevice) => void
  onAssociateSpl: (device: PlaybackDevice) => void
  onPlayTest: (device: PlaybackDevice) => void
  onStop: (device: PlaybackDevice) => void
  onControl: (device: PlaybackDevice, action: string) => void
  onDelete: (device: PlaybackDevice) => void
  onEmptyAdd: () => void
}

/** 支持格式 BadgeListCell（最多 2 枚 + 「+N」tooltip） */
function FormatsCell({ formats }: { formats: string[] | null }) {
  if (!formats || formats.length === 0) return <span className='text-muted-foreground'>—</span>
  const visible = formats.slice(0, 2)
  const hidden = formats.slice(2)
  return (
    <div className='flex flex-wrap items-center gap-1'>
      {visible.map((format) => (
        <Badge key={format} variant='secondary' className='rounded-md px-1.5 font-normal'>
          {format}
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
              {hidden.map((format) => (
                <Badge key={format} variant='secondary' className='rounded-md px-1.5 font-normal'>
                  {format}
                </Badge>
              ))}
            </div>
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  )
}

export function PlaybackDeviceTable(props: PlaybackDeviceTableProps) {
  const isEmpty = !props.loading && props.rows.length === 0
  const allSelected =
    !isEmpty && props.rows.length > 0 && props.selectedIds.size === props.rows.length

  if (props.loading) {
    return (
      <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
        <Skeleton className='h-10 w-full rounded-none border-b' />
        {Array.from({ length: Math.min(props.total || 5, 6) }).map((_, i) => (
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
            <Headphones aria-hidden='true' className='size-4' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>{props.searchKeyword ? '未找到匹配的播放设备' : '暂无播放设备'}</EmptyTitle>
            <EmptyDescription>
              {props.searchKeyword
                ? '换个关键词或清除筛选条件试试'
                : '点击右上角「添加播放设备」登记第一台设备，或调整筛选条件'}
            </EmptyDescription>
          </EmptyHeader>
          {!props.searchKeyword && (
            <EmptyContent>
              <Button variant='outline' size='sm' onClick={props.onEmptyAdd}>
                <Box aria-hidden='true' className='size-3.5' />
                添加播放设备
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
        <table className='w-full min-w-[1050px] text-[13px]'>
          <thead>
            <tr className='bg-[var(--table-header)] text-xs'>
              {props.batchMode && (
                <th className='w-11 px-2.5 py-2'>
                  <span className='flex items-center justify-center'>
                    <Checkbox
                      aria-label='全选当前页'
                      checked={allSelected}
                      onCheckedChange={props.onToggleSelectAll}
                    />
                  </span>
                </th>
              )}
              <th className='w-[72px] px-3 py-2 text-left font-medium'>ID</th>
              <th className='px-3 py-2 text-left font-medium'>名称</th>
              <th className='px-3 py-2 text-left font-medium'>状态</th>
              <th className='px-3 py-2 text-left font-medium'>设备类型</th>
              <th className='px-3 py-2 text-left font-medium'>所属实验室</th>
              <th className='px-3 py-2 text-left font-medium'>支持的格式</th>
              <th className='px-3 py-2 text-left font-medium'>系统唯一标识</th>
              <th className='px-3 py-2 text-right font-medium'>支持的通道数</th>
              <th className='px-3 py-2 text-right font-medium'>采样率</th>
              <th className='px-3 py-2 text-left font-medium'>声压映射</th>
              <th className='px-3 py-2 text-left font-medium'>
                <button
                  type='button'
                  onClick={props.onSortChange}
                  className='hover:text-foreground inline-flex items-center gap-1 transition-colors'
                >
                  更新时间
                </button>
              </th>
              <th className='w-14 px-3 py-2 text-right font-medium'>操作</th>
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row) => {
              const isOffline = row.status === 'offline'
              const typeMeta = row.deviceType
                ? PLAYBACK_DEVICE_TYPE_META[row.deviceType]
                : null
              return (
                <tr
                  key={row.id}
                  className={cn(
                    'hover:bg-muted/40 border-border/50 border-b last:border-b-0',
                    isOffline && 'bg-muted/20 border-l-4 border-l-[var(--table-disabled)]',
                    props.selectedIds.has(row.id) && 'bg-primary/[0.04] dark:bg-primary/10'
                  )}
                >
                  {props.batchMode && (
                    <td className='px-2.5 py-2'>
                      <span className='flex items-center justify-center'>
                        <Checkbox
                          aria-label={`选择播放设备 ${row.name}`}
                          checked={props.selectedIds.has(row.id)}
                          onCheckedChange={() => props.onToggleSelect(row.id)}
                        />
                      </span>
                    </td>
                  )}
                  <td className='px-3 py-2'>
                    <span className='font-mono text-xs text-muted-foreground tabular-nums'>
                      #{row.id}
                    </span>
                  </td>
                  <td className='max-w-44 px-3 py-2'>
                    <span className='min-w-0 block truncate font-medium' title={row.name}>
                      {row.name}
                    </span>
                    {row.description && (
                      <span className='text-muted-foreground min-w-0 block truncate text-xs'>
                        {row.description}
                      </span>
                    )}
                  </td>
                  <td className='px-3 py-2'>
                    <DeviceStatusBadge status={row.status} occupied={row.occupied} />
                  </td>
                  <td className='px-3 py-2'>
                    {typeMeta ? (
                      <Badge variant='secondary' className='rounded-md px-1.5 font-normal'>
                        <AudioLines aria-hidden='true' className='size-3' />
                        {typeMeta.label}
                      </Badge>
                    ) : (
                      <span className='text-muted-foreground'>—</span>
                    )}
                  </td>
                  <td className='px-3 py-2'>
                    {row.labName ? (
                      <Badge variant='secondary' className='rounded-md px-1.5 font-normal'>
                        {row.labName}
                      </Badge>
                    ) : (
                      <span className='text-muted-foreground'>未绑定</span>
                    )}
                  </td>
                  <td className='max-w-40 px-3 py-2'>
                    <FormatsCell formats={row.supportedFormats} />
                  </td>
                  <td className='max-w-40 px-3 py-2'>
                    <span className='font-mono text-xs truncate'>{row.deviceUniqueId ?? '—'}</span>
                  </td>
                  <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                    {/* P4：通道数缺失显「—」而非 0 */}
                    {row.supportedChannels ?? (row.channelIndex != null ? row.channelIndex : '—')}
                  </td>
                  <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                    {row.sampleRate ? `${row.sampleRate} Hz` : '—'}
                  </td>
                  <td className='max-w-40 px-3 py-2'>
                    {row.currentSplMappingName ? (
                      <Badge variant='outline' className='rounded-md px-1.5 font-normal'>
                        {row.currentSplMappingName}
                      </Badge>
                    ) : (
                      <span className='text-muted-foreground'>未关联</span>
                    )}
                  </td>
                  <td className='px-3 py-2 font-mono text-xs tabular-nums'>
                    {row.updatedAt ? row.updatedAt.replace('T', ' ').slice(0, 16) : '—'}
                  </td>
                  <td className='px-3 py-2'>
                    <div className='flex items-center justify-end gap-0.5'>
                      <DeviceRowActions
                        kind='playback'
                        device={row}
                        canRead={props.canRead}
                        canUpdate={props.canUpdate}
                        canDelete={props.canDelete}
                        canControl={props.canControl}
                        canHealth={props.canHealth}
                        canPlaybackControl={props.canControl}
                        onDetail={() => props.onDetail(row)}
                        onEdit={() => props.onEdit(row)}
                        onHealth={() => undefined}
                        onTest={() => undefined}
                        onStopTest={() => undefined}
                        onControl={(action) => props.onControl(row, action)}
                        onDelete={() => props.onDelete(row)}
                        onAssociateSpl={() => props.onAssociateSpl(row)}
                        onPlayTest={() => props.onPlayTest(row)}
                        onStop={() => props.onStop(row)}
                        onInstallApp={() => undefined}
                        onUninstallApp={() => undefined}
                      />
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

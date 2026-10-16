/**
 * 测试设备列表数据表（16_设备域.md §3.4；DataTablePage 对位）。
 * 列：☑选择/ID/设备名称(+描述)/状态(五态+「测试中」占用叠加态)/所属实验室/系统/型号/序列号(+复制)/
 * 连接方式/应用/支持算法(最多2枚+「+N」)/驱动/提示词/最后在线/操作。
 * INT-487：所属实验室列 Badge secondary「{lab_name}」/未绑定 muted「未绑定」（DTO 未暴露前规范隐藏，
 * mock 先行）；「测试中」占用态=状态位叠加 info 徽章+脉冲动画，不参与五态筛选/统计。
 * 离线行按状态机禁用相关行操作（§3.4.1），被占用设备显「停止测试」。
 */
import { Circle, CircleCheck, Server } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { CopyButton } from '@/components/copy-button'
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
import type { TestDevice } from '@/domain/models/testDevice'
import { DeviceStatusBadge } from '@/features/devices/components/device-status-badge'
import { DeviceRowActions } from '@/features/devices/components/device-row-actions'

export interface TestDeviceTableProps {
  rows: TestDevice[]
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
  onDetail: (device: TestDevice) => void
  onEdit: (device: TestDevice) => void
  onHealth: (device: TestDevice) => void
  onTest: (device: TestDevice) => void
  onStopTest: (device: TestDevice) => void
  onControl: (device: TestDevice, action: string) => void
  onDelete: (device: TestDevice) => void
  onEmptyAdd: () => void
}

/** 支持算法 BadgeListCell（最多 2 枚 + 「+N」tooltip 全量） */
function AlgorithmsCell({ algorithms }: { algorithms: string[] | null }) {
  if (!algorithms || algorithms.length === 0) {
    return <span className='text-muted-foreground'>—</span>
  }
  const visible = algorithms.slice(0, 2)
  const hidden = algorithms.slice(2)
  return (
    <div className='flex flex-wrap items-center gap-1'>
      {visible.map((algo) => (
        <Badge key={algo} variant='secondary' className='rounded-md px-1.5 font-normal'>
          {algo}
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
              {hidden.map((algo) => (
                <Badge key={algo} variant='secondary' className='rounded-md px-1.5 font-normal'>
                  {algo}
                </Badge>
              ))}
            </div>
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  )
}

export function TestDeviceTable(props: TestDeviceTableProps) {
  const isEmpty = !props.loading && props.rows.length === 0
  const allSelected =
    !isEmpty && props.rows.length > 0 && props.selectedIds.size === props.rows.length

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
            <Server aria-hidden='true' className='size-4' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>
              {props.searchKeyword ? '未找到匹配的设备' : '暂无设备'}
            </EmptyTitle>
            <EmptyDescription>
              {props.searchKeyword
                ? '换个关键词或清除筛选条件试试'
                : '点击右上角「添加设备」登记第一台设备，或调整筛选条件'}
            </EmptyDescription>
          </EmptyHeader>
          {!props.searchKeyword && (
            <EmptyContent>
              <Button variant='outline' size='sm' onClick={props.onEmptyAdd}>
                <Server aria-hidden='true' className='size-3.5' />
                添加设备
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
        <table className='w-full min-w-[1150px] text-[13px]'>
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
              <th className='px-3 py-2 text-left font-medium'>设备名称</th>
              <th className='px-3 py-2 text-left font-medium'>状态</th>
              <th className='px-3 py-2 text-left font-medium'>所属实验室</th>
              <th className='px-3 py-2 text-left font-medium'>系统</th>
              <th className='px-3 py-2 text-left font-medium'>型号</th>
              <th className='px-3 py-2 text-left font-medium'>序列号</th>
              <th className='px-3 py-2 text-left font-medium'>连接方式</th>
              <th className='px-3 py-2 text-left font-medium'>应用</th>
              <th className='px-3 py-2 text-left font-medium'>支持算法</th>
              <th className='px-3 py-2 text-left font-medium'>驱动</th>
              <th className='w-[52px] px-3 py-2 text-center font-medium'>提示词</th>
              <th className='px-3 py-2 text-left font-medium'>
                <button
                  type='button'
                  onClick={props.onSortChange}
                  className='hover:text-foreground inline-flex items-center gap-1 transition-colors'
                >
                  最后在线
                </button>
              </th>
              <th className='w-14 px-3 py-2 text-right font-medium'>操作</th>
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row) => {
              const isOffline = row.status === 'offline'
              return (
                <tr
                  key={row.id}
                  className={cn(
                    'hover:bg-muted/40 border-border/50 border-b last:border-b-0',
                    isOffline && 'bg-muted/20',
                    props.selectedIds.has(row.id) && 'bg-primary/[0.04] dark:bg-primary/10'
                  )}
                >
                  {props.batchMode && (
                    <td className='px-2.5 py-2'>
                      <span className='flex items-center justify-center'>
                        <Checkbox
                          aria-label={`选择设备 ${row.name}`}
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
                  <td className='max-w-48 px-3 py-2'>
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
                    {row.labName ? (
                      <Badge variant='secondary' className='rounded-md px-1.5 font-normal'>
                        {row.labName}
                      </Badge>
                    ) : (
                      <span className='text-muted-foreground'>未绑定</span>
                    )}
                  </td>
                  <td className='px-3 py-2'>
                    {row.system ? (
                      <Badge variant='outline' className='rounded-md px-1.5 font-normal'>
                        {row.system}
                      </Badge>
                    ) : (
                      <span className='text-muted-foreground'>—</span>
                    )}
                  </td>
                  <td className='max-w-32 px-3 py-2'>
                    <span className='min-w-0 block truncate'>{row.model ?? '—'}</span>
                  </td>
                  <td className='px-3 py-2'>
                    <span className='inline-flex items-center gap-1'>
                      <span className='font-mono text-xs truncate'>{row.serialNumber ?? '—'}</span>
                      {row.serialNumber && (
                        <CopyButton value={row.serialNumber} size='icon' className='size-5' aria-label='复制序列号' />
                      )}
                    </span>
                  </td>
                  <td className='px-3 py-2'>
                    <Badge variant='secondary' className='rounded-md px-1.5 font-normal'>
                      {row.connectionType === 'remote' ? '远程连接' : 'USB连接'}
                    </Badge>
                    {row.connectionType === 'remote' && row.ip && (
                      <span className='text-muted-foreground block text-xs'>
                        {row.ip}:5555
                      </span>
                    )}
                  </td>
                  <td className='max-w-40 px-3 py-2'>
                    {row.appName ? (
                      <span className='min-w-0 block truncate text-xs'>
                        {row.appName}
                        {row.appVersion ? ` · ${row.appVersion}` : ''}
                      </span>
                    ) : (
                      <span className='text-muted-foreground'>—</span>
                    )}
                  </td>
                  <td className='max-w-40 px-3 py-2'>
                    <AlgorithmsCell algorithms={row.supportedAlgorithms} />
                  </td>
                  <td className='max-w-28 px-3 py-2'>
                    <span className='min-w-0 block truncate'>{row.driverName ?? '—'}</span>
                  </td>
                  <td className='px-3 py-2 text-center'>
                    {row.needsPromptAudio ? (
                      <Tooltip>
                        <TooltipTrigger
                          render={
                            <CircleCheck
                              aria-label='需要提示词'
                              className='text-success mx-auto size-4'
                            />
                          }
                        />
                        <TooltipContent>需要提示词</TooltipContent>
                      </Tooltip>
                    ) : (
                      <Circle aria-hidden='true' className='text-muted-foreground mx-auto size-4' />
                    )}
                  </td>
                  <td className='px-3 py-2 font-mono text-xs tabular-nums'>
                    {row.lastOnlineAt ? row.lastOnlineAt.replace('T', ' ').slice(0, 16) : '—'}
                  </td>
                  <td className='px-3 py-2'>
                    <div className='flex items-center justify-end gap-0.5'>
                      <DeviceRowActions
                        kind='test'
                        device={row}
                        canRead={props.canRead}
                        canUpdate={props.canUpdate}
                        canDelete={props.canDelete}
                        canControl={props.canControl}
                        canPlaybackControl={false}
                        onDetail={() => props.onDetail(row)}
                        onEdit={() => props.onEdit(row)}
                        onHealth={() => props.onHealth(row)}
                        onTest={() => props.onTest(row)}
                        onStopTest={() => props.onStopTest(row)}
                        onControl={(action) => props.onControl(row, action)}
                        onDelete={() => props.onDelete(row)}
                        onAssociateSpl={() => undefined}
                        onPlayTest={() => undefined}
                        onResultAnalysis={() => undefined}
                        onDiagnose={() => undefined}
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

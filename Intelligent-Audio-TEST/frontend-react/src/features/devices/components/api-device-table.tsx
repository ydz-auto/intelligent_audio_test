/**
 * 测试 API 列表数据表（16_设备域.md §3.6；DataTablePage 对位）。
 * 列：☑选择/ID/API名称(+vendor)/协议/环境/状态/算法/端点数/默认并发/健康分(Progress h-1+tabular)/
 * RMS-SPL 默认映射/更新时间/操作。API 不挂实验室维度（§3.6 注 / INT-487）。
 * 主行右侧 ChevronRight 展开行：端点明细 StaticDataTable（URL/名称/优先级/最大进程/超时/音频时长/状态）。
 * 离线 API 行 DISABLED_ROW + Checkbox 禁用 + Tooltip「API 离线，无法执行测试」（§3.6 注）。
 */
import { BadgeCheck, ChevronDown, ChevronRight, Cloud, Link2Off } from 'lucide-react'
import { Fragment, useState } from 'react'

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
import { Progress } from '@/features/tasks/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { ApiDevice } from '@/domain/models/apiDevice'
import { API_ENV_META, API_PROTOCOL_META } from '@/domain/models/apiDevice'
import { DeviceRowActions } from '@/features/devices/components/device-row-actions'

export interface ApiDeviceTableProps {
  rows: ApiDevice[]
  loading: boolean
  total: number
  searchKeyword: string
  selectedIds: Set<number>
  batchMode: boolean
  onToggleSelect: (id: number) => void
  onToggleSelectAll: () => void
  canRead: boolean
  canUpdate: boolean
  canDelete: boolean
  canControl: boolean
  onDetail: (device: ApiDevice) => void
  onEdit: (device: ApiDevice) => void
  onHealth: (device: ApiDevice) => void
  onStopTest: (device: ApiDevice) => void
  onDelete: (device: ApiDevice) => void
  onEmptyAdd: () => void
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className='text-muted-foreground'>—</span>
  return (
    <Badge
      variant='outline'
      className={cn(
        'gap-1.5 px-2 font-normal',
        status === 'online' && 'text-success border-success/30 bg-success/10',
        status === 'offline' && 'text-muted-foreground'
      )}
    >
      <span
        aria-hidden='true'
        className={cn(
          'size-1.5 rounded-full',
          status === 'online' ? 'bg-[var(--success)]' : 'bg-[var(--muted-foreground)]'
        )}
      />
      {status === 'online' ? '在线' : '离线'}
    </Badge>
  )
}

export function ApiDeviceTable(props: ApiDeviceTableProps) {
  const isEmpty = !props.loading && props.rows.length === 0
  const allSelected =
    !isEmpty && props.rows.length > 0 && props.selectedIds.size === props.rows.length
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())

  const toggleExpanded = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  if (props.loading) {
    return (
      <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
        <Skeleton className='h-10 w-full rounded-none border-b' />
        {Array.from({ length: Math.min(props.total || 4, 6) }).map((_, i) => (
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
            <Cloud aria-hidden='true' className='size-4' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>{props.searchKeyword ? '未找到匹配的 API' : '暂无测试 API'}</EmptyTitle>
            <EmptyDescription>
              {props.searchKeyword
                ? '换个关键词或清除筛选条件试试'
                : '点击右上角「添加测试API」登记第一个接口，或调整筛选条件'}
            </EmptyDescription>
          </EmptyHeader>
          {!props.searchKeyword && (
            <EmptyContent>
              <Button variant='outline' size='sm' onClick={props.onEmptyAdd}>
                <Cloud aria-hidden='true' className='size-3.5' />
                添加测试API
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
              <th className='px-3 py-2 text-left font-medium'>API 名称</th>
              <th className='px-3 py-2 text-left font-medium'>协议</th>
              <th className='px-3 py-2 text-left font-medium'>环境</th>
              <th className='px-3 py-2 text-left font-medium'>状态</th>
              <th className='px-3 py-2 text-left font-medium'>算法</th>
              <th className='px-3 py-2 text-right font-medium'>端点数</th>
              <th className='px-3 py-2 text-right font-medium'>默认并发</th>
              <th className='w-32 px-3 py-2 text-left font-medium'>健康分</th>
              <th className='px-3 py-2 text-left font-medium'>RMS-SPL 默认映射</th>
              <th className='px-3 py-2 text-left font-medium'>更新时间</th>
              <th className='w-14 px-3 py-2 text-right font-medium'>操作</th>
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row) => {
              const offline = row.status === 'offline'
              const expanded = expandedIds.has(row.id)
              const protocolLabel = row.protocol
                ? API_PROTOCOL_META[row.protocol] ?? row.protocol
                : '—'
              const envLabel = row.environment
                ? API_ENV_META[row.environment] ?? row.environment
                : null
              return (
                <Fragment key={row.id}>
                  <tr
                    className={cn(
                      'hover:bg-muted/40 border-border/50 border-b last:border-b-0',
                      offline && 'bg-muted/20',
                      props.selectedIds.has(row.id) && 'bg-primary/[0.04] dark:bg-primary/10'
                    )}
                  >
                    {props.batchMode && (
                      <td className='px-2.5 py-2'>
                        <span className='flex items-center justify-center'>
                          <Tooltip>
                            <TooltipTrigger
                              render={
                                <span className='inline-flex'>
                                  <Checkbox
                                    aria-label={`选择 API ${row.name}`}
                                    checked={props.selectedIds.has(row.id)}
                                    disabled={offline}
                                    onCheckedChange={() => props.onToggleSelect(row.id)}
                                  />
                                </span>
                              }
                            />
                            {offline && <TooltipContent>API 离线，无法执行测试</TooltipContent>}
                          </Tooltip>
                        </span>
                      </td>
                    )}
                    <td className='px-3 py-2'>
                      <span className='font-mono text-xs text-muted-foreground tabular-nums'>
                        #{row.id}
                      </span>
                    </td>
                    <td className='max-w-52 px-3 py-2'>
                      <span className='min-w-0 flex items-center gap-1 font-medium'>
                        <button
                          type='button'
                          className='min-w-0 truncate text-start hover:text-primary transition-colors'
                          onClick={() => toggleExpanded(row.id)}
                          aria-expanded={expanded}
                        >
                          {row.name}
                        </button>
                        {expanded ? (
                          <ChevronDown aria-hidden='true' className='text-muted-foreground size-3.5 shrink-0' />
                        ) : (
                          <ChevronRight aria-hidden='true' className='text-muted-foreground size-3.5 shrink-0' />
                        )}
                      </span>
                      {row.vendor && (
                        <span className='text-muted-foreground min-w-0 block truncate text-xs'>
                          {row.vendor}
                        </span>
                      )}
                    </td>
                    <td className='px-3 py-2'>
                      <Badge variant='outline' className='rounded-md px-1.5 font-normal'>
                        {protocolLabel}
                      </Badge>
                    </td>
                    <td className='px-3 py-2'>
                      {envLabel ? (
                        <Badge variant='secondary' className='rounded-md px-1.5 font-normal'>
                          {envLabel}
                        </Badge>
                      ) : (
                        <span className='text-muted-foreground'>—</span>
                      )}
                    </td>
                    <td className='px-3 py-2'>
                      <StatusBadge status={row.status} />
                    </td>
                    <td className='px-3 py-2'>
                      <Badge variant='secondary' className='rounded-md px-1.5 font-normal'>
                        {row.algorithmType ?? '—'}
                      </Badge>
                    </td>
                    <td className='px-3 py-2 text-right text-xs tabular-nums'>
                      {row.endpoints.length > 0 ? `${row.endpoints.length} 个` : '0 个'}
                    </td>
                    <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                      {row.defaultMaxProcess ?? '—'}
                    </td>
                    <td className='px-3 py-2'>
                      {row.healthScore != null ? (
                        <span className='inline-flex w-full max-w-28 items-center gap-1.5'>
                          <Progress value={row.healthScore} size='xs' className='w-16' />
                          <span className='font-mono text-xs tabular-nums'>{row.healthScore}</span>
                        </span>
                      ) : (
                        <span className='text-muted-foreground'>—</span>
                      )}
                    </td>
                    <td className='max-w-40 px-3 py-2'>
                      {row.rmsSplMappingName ? (
                        <Badge variant='outline' className='gap-1 rounded-md px-1.5 font-normal'>
                          <BadgeCheck aria-hidden='true' className='text-success size-3' />
                          {row.rmsSplMappingName}
                        </Badge>
                      ) : (
                        <span className='text-muted-foreground text-xs'>
                          未关联
                          <Link2Off aria-hidden='true' className='text-muted-foreground ms-1 inline size-3' />
                        </span>
                      )}
                    </td>
                    <td className='px-3 py-2 font-mono text-xs tabular-nums'>
                      {row.updatedAt ? row.updatedAt.replace('T', ' ').slice(0, 16) : '—'}
                    </td>
                    <td className='px-3 py-2'>
                      <div className='flex items-center justify-end gap-0.5'>
                        <DeviceRowActions
                          kind='api'
                          device={row}
                          canRead={props.canRead}
                          canUpdate={props.canUpdate}
                          canDelete={props.canDelete}
                          canControl={props.canControl}
                          canPlaybackControl={false}
                          onDetail={() => props.onDetail(row)}
                          onEdit={() => props.onEdit(row)}
                          onHealth={() => props.onHealth(row)}
                          onTest={() => undefined}
                          onStopTest={() => props.onStopTest(row)}
                          onControl={() => undefined}
                          onDelete={() => props.onDelete(row)}
                          onAssociateSpl={() => undefined}
                          onPlayTest={() => undefined}
                          onResultAnalysis={() => undefined}
                          onDiagnose={() => undefined}
                        />
                      </div>
                    </td>
                  </tr>
                  {expanded && (
                    <tr className='border-border/50 border-b bg-muted/30'>
                      <td colSpan={props.batchMode ? 13 : 12} className='px-4 py-2.5'>
                        <div className='text-muted-foreground mb-1.5 text-xs'>端点明细</div>
                        <table className='w-full text-xs'>
                          <thead>
                            <tr className='bg-[var(--table-header)] text-xs text-muted-foreground'>
                              <th className='px-2 py-1.5 text-left font-medium'>URL</th>
                              <th className='px-2 py-1.5 text-left font-medium'>名称</th>
                              <th className='px-2 py-1.5 text-right font-medium'>优先级</th>
                              <th className='px-2 py-1.5 text-right font-medium'>最大进程</th>
                              <th className='px-2 py-1.5 text-right font-medium'>超时</th>
                              <th className='px-2 py-1.5 text-right font-medium'>音频时长</th>
                              <th className='px-2 py-1.5 text-left font-medium'>状态</th>
                            </tr>
                          </thead>
                          <tbody>
                            {row.endpoints.length === 0 ? (
                              <tr>
                                <td colSpan={7} className='text-muted-foreground px-2 py-3 text-center'>
                                  暂无端点，请在编辑弹窗中配置
                                </td>
                              </tr>
                            ) : (
                              row.endpoints.map((ep) => (
                                <tr key={ep.id ?? ep.endpoint} className='border-border/40 border-b last:border-b-0'>
                                  <td className='max-w-56 px-2 py-1.5 font-mono truncate'>{ep.endpoint}</td>
                                  <td className='px-2 py-1.5'>{ep.name ?? '—'}</td>
                                  <td className='px-2 py-1.5 text-right tabular-nums'>{ep.priority ?? '—'}</td>
                                  <td className='px-2 py-1.5 text-right tabular-nums'>{ep.maxProcess ?? '—'}</td>
                                  <td className='px-2 py-1.5 text-right tabular-nums'>
                                    {ep.maxTimeout != null ? `${ep.maxTimeout}s` : '—'}
                                  </td>
                                  <td className='px-2 py-1.5 text-right tabular-nums'>
                                    {ep.maxAudioDuration != null ? `${ep.maxAudioDuration}s` : '—'}
                                  </td>
                                  <td className='px-2 py-1.5'>
                                    <StatusBadge status={ep.status} />
                                  </td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

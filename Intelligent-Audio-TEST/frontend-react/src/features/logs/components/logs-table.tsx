/**
 * 日志数据表（features/logs；17_配置运维.md §4.4，DataTablePage 对位）。
 * 列=勾选/展开/时间/级别/模块/算法/来源/内容/操作；ERROR/CRITICAL 行染 rose tint、
 * marked 行首列 border-l-4 标记色；行点击展开详情行（时间/级别/分类/模块/算法类型/
 * 来源/设备ID/任务ID/线程ID/内容 + pre 上下文 JSON）。移动端（≤640px）出卡片。
 * 空态/加载/错误态齐全（§3.3：加载/空态/错误态一个不少）。
 */
import { ChevronDown, ChevronUp } from 'lucide-react'
import { Fragment, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { useMediaQuery } from '@/hooks/use-media-query'
import type { Log } from '@/domain/models/log'
import { LOG_MARK_OPTIONS } from '@/domain/models/log'
import { LOG_LEVEL_META, LOG_MARK_META, formatLogTime } from '@/features/logs/constants'
import { cn } from '@/lib/utils'

export type LogsTableProps = {
  rows: Log[]
  loading: boolean
  error: boolean
  onRetry: () => void
  /** 是否存在筛选条件（搜索空态文案「未找到匹配日志」判定） */
  hasActiveFilters: boolean
  selectedIds: Set<number>
  onToggleSelect: (id: number) => void
  onToggleSelectAll: (ids: number[]) => void
  /** log:manage（行内「标记」权限） */
  canManage: boolean
  onMarkColor: (logId: number, color: string) => void
  onCopy: (log: Log) => void
  sortOrder: 'desc' | 'asc'
  onSortChange: () => void
}

/** 行内标记色 Popover（§4.4 操作列「标记」） */
function RowMarkPopover({
  log,
  onMarkColor,
}: {
  log: Log
  onMarkColor: (logId: number, color: string) => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button variant='ghost' size='sm' className='h-7 px-2 text-xs'>
            标记
          </Button>
        }
      />
      <PopoverContent className='w-36 p-1.5'>
        <div className='grid gap-0.5'>
          {LOG_MARK_OPTIONS.map((option) => (
            <button
              key={option.value}
              type='button'
              className='hover:bg-muted flex items-center gap-2 rounded-md px-2 py-1.5 text-xs'
              onClick={() => {
                onMarkColor(log.id, option.value)
                setOpen(false)
              }}
            >
              <span aria-hidden='true' className={cn('size-2.5 rounded-full', LOG_MARK_META[option.value]?.dotClass)} />
              {option.label}
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}

/** 详情内容（桌面 tr/td 与移动 div 共用） */
function LogDetailContent({ log }: { log: Log }) {
  const detail = [
    ['时间', formatLogTime(log.time)],
    ['级别', log.level.toUpperCase()],
    ['分类', log.category || '—'],
    ['模块', log.module || '—'],
    ['算法类型', log.algorithmType || '—'],
    ['来源', log.source || '—'],
    ['设备ID', log.deviceId ?? '—'],
    ['任务ID', log.taskId ?? '—'],
    ['线程ID', log.threadId ?? '—'],
  ] as const
  const context = {
    category: log.category,
    deviceId: log.deviceId,
    taskId: log.taskId,
    threadId: log.threadId,
    algorithmType: log.algorithmType,
  }
  return (
    <>
      <div className='text-muted-foreground grid gap-x-8 gap-y-1 text-xs sm:grid-cols-2 lg:grid-cols-3'>
        {detail.map(([label, value]) => (
          <div key={label} className='flex gap-2'>
            <span className='shrink-0 font-medium'>{label}</span>
            <span className='min-w-0 truncate tabular-nums'>{value}</span>
          </div>
        ))}
        <div className='sm:col-span-2 lg:col-span-3'>
          <div className='font-medium'>内容</div>
          <div className='text-muted-foreground mt-0.5 whitespace-pre-wrap break-all'>{log.content || '—'}</div>
        </div>
      </div>
      <details className='mt-2'>
        <summary className='text-muted-foreground cursor-pointer text-xs'>上下文信息</summary>
        <pre className='bg-muted/40 mt-1 overflow-x-auto rounded-md p-2 text-xs'>{JSON.stringify(context, null, 2)}</pre>
      </details>
    </>
  )
}

/** 桌面详情行（§4.4 DetailSection） */
function LogDetailRow({ log, expanded }: { log: Log; expanded: boolean }) {
  return (
    <tr className={cn('border-border/60 border-b', expanded ? 'table-row' : 'hidden')}>
      <td colSpan={9} className='bg-muted/20 px-4 py-3'>
        <LogDetailContent log={log} />
      </td>
    </tr>
  )
}

/** 移动端详情卡片 */
function LogDetailCard({ log, expanded }: { log: Log; expanded: boolean }) {
  if (!expanded) return null
  return (
    <div className='border-border/60 bg-muted/20 rounded-lg border p-3'>
      <LogDetailContent log={log} />
    </div>
  )
}

export function LogsTable(props: LogsTableProps) {
  const {
    rows,
    loading,
    error,
    onRetry,
    hasActiveFilters,
    selectedIds,
    onToggleSelect,
    onToggleSelectAll,
    canManage,
    onMarkColor,
    onCopy,
    sortOrder,
    onSortChange,
  } = props

  const isMobile = useMediaQuery('(max-width: 640px)')
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())

  const toggleExpanded = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const allSelected = rows.length > 0 && rows.every((row) => selectedIds.has(row.id))

  /** 行染 tint + marked 色条（§4.4） */
  const rowClass = (log: Log) =>
    cn(
      'hover:bg-muted/40 transition-colors',
      LOG_LEVEL_META[log.level]?.tint,
      log.mark && LOG_MARK_META[log.mark] && cn('border-l-4', LOG_MARK_META[log.mark].barClass)
    )

  if (error) {
    return (
      <Empty className='h-80'>
        <EmptyHeader>
          <EmptyMedia variant='icon' />
          <EmptyTitle>日志加载失败</EmptyTitle>
          <EmptyDescription>请检查网络后重试</EmptyDescription>
        </EmptyHeader>
        <Button variant='outline' size='sm' onClick={onRetry}>
          重试
        </Button>
      </Empty>
    )
  }

  if (loading && rows.length === 0) {
    return (
      <div className='bg-card ring-border/60 rounded-xl p-2 ring-1'>
        <div className='flex items-center gap-4 border-b px-3 py-2'>
          {Array.from({ length: 7 }).map((_, i) => (
            <Skeleton key={i} className='h-4 flex-1' />
          ))}
        </div>
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className='mx-3 my-2 h-8' />
        ))}
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <Empty className='h-80'>
        <EmptyHeader>
          <EmptyMedia variant='icon' />
          <EmptyTitle>{hasActiveFilters ? '未找到匹配日志' : '暂无日志'}</EmptyTitle>
          <EmptyDescription>
            {hasActiveFilters
              ? '换个关键词或清除筛选条件试试'
              : '日志将出现在 API 调用或测试执行之后'}
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  if (isMobile) {
    return (
      <div className='flex flex-col gap-2'>
        {rows.map((log) => {
          const expanded = expandedIds.has(log.id)
          const selected = selectedIds.has(log.id)
          return (
            <Fragment key={log.id}>
              <div
                className={cn(
                  'border-border/60 bg-card rounded-lg border p-2.5',
                  selected && 'border-primary/40 bg-primary/[0.03]',
                  log.mark && LOG_MARK_META[log.mark] && cn('border-l-4', LOG_MARK_META[log.mark].barClass)
                )}
              >
                <div className='flex items-start gap-2'>
                  <Checkbox
                    aria-label={`选择日志 ${log.id}`}
                    className='mt-0.5'
                    checked={selected}
                    onCheckedChange={() => onToggleSelect(log.id)}
                  />
                  <button
                    type='button'
                    aria-expanded={expanded}
                    aria-label={expanded ? '收起详情' : '展开详情'}
                    className='mt-0.5'
                    onClick={() => toggleExpanded(log.id)}
                  >
                    {expanded ? <ChevronUp className='size-3.5' /> : <ChevronDown className='size-3.5' />}
                  </button>
                  <div className='min-w-0 flex-1'>
                    <div className='flex items-center justify-between gap-2'>
                      <StatusBadge
                        label={log.level.toUpperCase()}
                        variant={LOG_LEVEL_META[log.level]?.variant ?? 'neutral'}
                        size='sm'
                      />
                      <span className='text-muted-foreground shrink-0 font-mono text-[11px] tabular-nums'>
                        {formatLogTime(log.time)}
                      </span>
                    </div>
                    <div className='mt-1 line-clamp-2 break-all text-sm' title={log.content}>
                      {log.content}
                    </div>
                    <div className='text-muted-foreground mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px]'>
                      {log.module && <span>{log.module}</span>}
                      {log.algorithmType && <span>{log.algorithmType}</span>}
                      {log.source && <span>{log.source}</span>}
                    </div>
                    <div className='mt-1.5 flex items-center gap-1'>
                      {canManage && <RowMarkPopover log={log} onMarkColor={onMarkColor} />}
                      <Button variant='ghost' size='sm' className='h-7 px-2 text-xs' onClick={() => onCopy(log)}>
                        复制
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
              {expanded && <LogDetailCard log={log} expanded />}
            </Fragment>
          )
        })}
      </div>
    )
  }

  return (
    <div className='bg-card ring-border/60 overflow-hidden rounded-xl ring-1'>
      <div className='overflow-x-auto'>
        <table className='w-full min-w-[900px] text-[13px]'>
          <thead className='bg-[var(--table-header)]'>
            <tr className='text-muted-foreground text-xs'>
              <th className='w-11 px-2 py-2.5 text-left font-medium'>
                <Checkbox
                  aria-label='全选当前页'
                  checked={allSelected}
                  onCheckedChange={() => onToggleSelectAll(rows.map((row) => row.id))}
                />
              </th>
              <th className='w-9 px-1 py-2.5' />
              <th className='px-2 py-2.5 text-left font-medium'>
                <button type='button' className='inline-flex items-center gap-1' onClick={onSortChange}>
                  时间
                  {sortOrder === 'desc' ? <ChevronDown className='size-3' /> : <ChevronUp className='size-3' />}
                </button>
              </th>
              <th className='px-2 py-2.5 text-left font-medium'>级别</th>
              <th className='px-2 py-2.5 text-left font-medium'>模块</th>
              <th className='px-2 py-2.5 text-left font-medium'>算法</th>
              <th className='px-2 py-2.5 text-left font-medium'>来源</th>
              <th className='px-2 py-2.5 text-left font-medium'>内容</th>
              <th className='px-2 py-2.5 text-right font-medium'>操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((log) => {
              const expanded = expandedIds.has(log.id)
              const selected = selectedIds.has(log.id)
              return (
                <Fragment key={log.id}>
                  <tr
                    data-state={selected ? 'selected' : undefined}
                    className={cn(rowClass(log), selected && 'bg-primary/[0.04] dark:bg-primary/10')}
                    onClick={() => toggleExpanded(log.id)}
                  >
                    <td className='px-2 py-2 align-top'>
                      <Checkbox
                        aria-label={`选择日志 ${log.id}`}
                        checked={selected}
                        onClick={(event) => event.stopPropagation()}
                        onCheckedChange={() => onToggleSelect(log.id)}
                      />
                    </td>
                    <td className='px-1 py-2 align-top'>
                      <button
                        type='button'
                        aria-expanded={expanded}
                        aria-label={expanded ? '收起详情' : '展开详情'}
                        onClick={(event) => event.stopPropagation()}
                      >
                        {expanded ? <ChevronUp className='size-4' /> : <ChevronDown className='size-4' />}
                      </button>
                    </td>
                    <td className='text-muted-foreground px-2 py-2 font-mono text-xs align-top whitespace-nowrap tabular-nums'>
                      {formatLogTime(log.time)}
                    </td>
                    <td className='px-2 py-2 align-top'>
                      <StatusBadge
                        label={log.level.toUpperCase()}
                        variant={LOG_LEVEL_META[log.level]?.variant ?? 'neutral'}
                        size='sm'
                      />
                    </td>
                    <td className='px-2 py-2 align-top'>
                      {log.module ? (
                        <Badge variant='secondary'>{log.module}</Badge>
                      ) : (
                        <span className='text-muted-foreground'>—</span>
                      )}
                    </td>
                    <td className='px-2 py-2 align-top'>
                      {log.algorithmType ? (
                        <span className='border-border/60 bg-muted/30 inline-flex max-w-full items-center rounded-md border px-2 py-0.5 text-xs whitespace-nowrap'>
                          {log.algorithmType}
                        </span>
                      ) : (
                        <span className='text-muted-foreground'>—</span>
                      )}
                    </td>
                    <td className='text-muted-foreground px-2 py-2 align-top text-xs'>{log.source || '—'}</td>
                    <td className='max-w-[280px] px-2 py-2 align-top'>
                      <div className='flex items-start gap-1.5'>
                        {log.mark && LOG_MARK_META[log.mark] && (
                          <span
                            aria-hidden='true'
                            className={cn('mt-1.5 size-1.5 shrink-0 rounded-full', LOG_MARK_META[log.mark].dotClass)}
                          />
                        )}
                        <span className='line-clamp-2 min-w-0 break-all' title={log.content}>
                          {log.content}
                        </span>
                      </div>
                    </td>
                    <td className='px-2 py-2 text-right align-top'>
                      <div className='flex items-center justify-end gap-0.5'>
                        {canManage && <RowMarkPopover log={log} onMarkColor={onMarkColor} />}
                        <Button variant='ghost' size='sm' className='h-7 px-2 text-xs' onClick={() => onCopy(log)}>
                          复制
                        </Button>
                      </div>
                    </td>
                  </tr>
                  <LogDetailRow log={log} expanded={expanded} />
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

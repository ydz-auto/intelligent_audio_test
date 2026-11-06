/**
 * 日志数据表（interfaces 层；17_配置运维.md §4.4 DataTablePage）。
 * 列=勾选/展开/时间/级别/模块/算法/来源/内容/操作；ERROR·CRITICAL 行染浅色 tint；
 * 时间/级别/模块/来源列头可点击排序（§4.4「时间=排序列」，客户端排序对齐 V9.7.10
 * sortLogs 语义，后端 LogListQuery 无 sort 参数）；行点击展开详情行（LogRowDetails）；
 * 行内操作「标记」（颜色 Popover，log:manage；仅历史库行——文件日志游标行后端只读
 * 不可标记，不给入口，INT-1945；选色即收，同色二次点击清除 / 已标记行另有「清除标记」，
 * 对齐 V9.7.10 开关语义，INT-1947）/「复制」（CopyButton，[时间] [级别] [模块] 内容）。
 * 空态：「暂无日志」/ 搜索空「未找到匹配日志」；加载 TableSkeleton；首载失败 ErrorState
 * + 重试（INT-607 错误态区分先例，错误态不渲染空态文案）。
 */
import { ArrowDown, ArrowUp, ArrowUpDown, Check, ChevronDown, ChevronRight, Flag, X } from 'lucide-react'
import { Fragment, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { CopyButton } from '@/components/copy-button'
import { ErrorState } from '@/components/error-state'
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
import { cn } from '@/lib/utils'
import { isFileLogId, nextLogMark, type LogItem } from '@/domain/models/log'
import {
  LOG_LEVEL_BADGE_VARIANT,
  LOG_LEVEL_ROW_TINT,
  LOG_MARK_COLORS,
} from '@/features/logs/constants'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { LogRowDetails } from '@/features/logs/components/log-row-details'

/** 可排序列（§4.4：时间/级别/模块/来源；与 V9.7.10 sortLogs 列一致） */
export type LogSortKey = 'time' | 'level' | 'module' | 'source'

export type LogSort = {
  key: LogSortKey
  direction: 'asc' | 'desc'
}

/** 级别排序权重（DEBUG < INFO < WARNING < ERROR < CRITICAL；未知级别垫底） */
const LOG_LEVEL_ORDER: Record<string, number> = {
  DEBUG: 0,
  INFO: 1,
  WARNING: 2,
  ERROR: 3,
  CRITICAL: 4,
}

/** 客户端排序（§4.4 排序列；null 不动序，realtime 增量插顶语义保留） */
export function sortLogItems(rows: LogItem[], sort: LogSort | null): LogItem[] {
  if (!sort) return rows
  const copy = [...rows]
  const { key, direction } = sort
  copy.sort((a, b) => {
    let cmp = 0
    switch (key) {
      case 'time':
        cmp = a.time.localeCompare(b.time)
        break
      case 'level':
        cmp = (LOG_LEVEL_ORDER[a.level.toUpperCase()] ?? 99) - (LOG_LEVEL_ORDER[b.level.toUpperCase()] ?? 99)
        break
      case 'module':
        cmp = (a.module || '').localeCompare(b.module || '')
        break
      case 'source':
        cmp = (a.source || '').localeCompare(b.source || '')
        break
    }
    return direction === 'asc' ? cmp : -cmp
  })
  return copy
}

export type LogsTableProps = {
  rows: LogItem[]
  loading: boolean
  /** 列表首载失败（INT-607：错误态区分，不落空态「暂无日志」误导） */
  error?: boolean
  onRetry?: () => void
  total: number
  searchKeyword: string
  selectedIds: Set<number>
  onToggleSelect: (id: number) => void
  onToggleSelectAll: () => void
  canManage: boolean
  expandedId: number | null
  onToggleExpand: (id: number) => void
  onMark: (log: LogItem, mark: string) => void
  /** 当前排序（null=服务端原序；realtime 增量插顶语义保留） */
  sort: LogSort | null
  onToggleSort: (key: LogSortKey) => void
}

/** 复制内容格式（§4.5「复制内容」口径：[时间] [级别] [模块] 内容） */
export function formatLogCopy(log: LogItem): string {
  return `[${log.time}] [${log.level}] [${log.module}] ${log.content}`
}

function MarkAction({
  log,
  canManage,
  onMark,
}: {
  log: LogItem
  canManage: boolean
  onMark: (log: LogItem, mark: string) => void
}) {
  /** 选色即收（§4.4 行内标记 Popover；INT-1947 修复「选完弹层不关」） */
  const [open, setOpen] = useState(false)
  // 文件日志行（审计 JSONL 游标）后端只读、不可标记，不给入口（INT-1945）
  if (!canManage || isFileLogId(log.id)) return null

  const current = log.mark ?? ''
  const selectMark = (mark: string) => {
    onMark(log, mark)
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant='ghost'
            size='icon'
            className='size-7'
            aria-label={`标记日志 ${log.id}`}
          >
            <Flag
              aria-hidden='true'
              className={cn('size-3.5', current && 'text-foreground')}
            />
          </Button>
        }
      />
      <PopoverContent align='end' className='w-40 p-1.5'>
        <div className='text-muted-foreground px-2 py-1 text-xs'>
          {current ? '重新标记或清除' : '选择标记颜色'}
        </div>
        <div className='grid grid-cols-2 gap-1'>
          {LOG_MARK_COLORS.map((color) => {
            const active = current === color.value
            return (
              <Button
                key={color.value}
                variant='ghost'
                size='sm'
                className='h-7 justify-start gap-2 text-xs'
                aria-pressed={active}
                title={active ? '再次点击清除标记' : undefined}
                onClick={() => selectMark(nextLogMark(current, color.value))}
              >
                <span
                  aria-hidden='true'
                  className={cn('size-2.5 rounded-full', color.swatch)}
                />
                {color.label}
                {active && <Check aria-hidden='true' className='ml-auto size-3' />}
              </Button>
            )
          })}
        </div>
        {/* V9.7.10 logView.ts:418-428 同色二次点击清除之外，给已标记行一条显式出口 */}
        {current && (
          <Button
            variant='ghost'
            size='sm'
            className='text-muted-foreground h-7 w-full justify-start gap-2 text-xs'
            onClick={() => selectMark('')}
          >
            <X aria-hidden='true' className='size-3.5' />
            清除标记
          </Button>
        )}
      </PopoverContent>
    </Popover>
  )
}

/** 排序列头（§4.4：可点击排序，箭头指示当前方向；未激活显示可排提示图标） */
function SortableHeader({
  sortKey,
  label,
  sort,
  onToggleSort,
}: {
  sortKey: LogSortKey
  label: string
  sort: LogSort | null
  onToggleSort: () => void
}) {
  const active = sort?.key === sortKey
  return (
    <button
      type='button'
      onClick={onToggleSort}
      aria-label={`按${label}排序`}
      className='hover:text-foreground inline-flex items-center gap-1 transition-colors'
    >
      {label}
      {active ? (
        sort!.direction === 'asc' ? (
          <ArrowUp aria-hidden='true' className='size-3' />
        ) : (
          <ArrowDown aria-hidden='true' className='size-3' />
        )
      ) : (
        <ArrowUpDown
          aria-hidden='true'
          className='text-muted-foreground/60 size-3 opacity-60'
        />
      )}
    </button>
  )
}

export function LogsTable(props: LogsTableProps) {
  const isEmpty = !props.loading && props.rows.length === 0
  // 首载失败：错误态优先于空态（INT-607「错误态区分」，不得把加载失败渲染成无数据）
  const hasError = Boolean(props.error) && isEmpty
  const allSelected =
    !isEmpty && props.rows.length > 0 && props.selectedIds.size === props.rows.length

  if (props.loading) {
    return (
      <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
        <Skeleton className='h-10 w-full rounded-none border-b' />
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className='h-12 w-full rounded-none border-b' />
        ))}
      </div>
    )
  }

  if (hasError) {
    return (
      <div className='bg-card ring-foreground/10 rounded-xl ring-1'>
        <ErrorState
          title='日志列表加载失败'
          description='获取日志列表失败，请重试'
          onRetry={props.onRetry}
        />
      </div>
    )
  }

  if (isEmpty) {
    return (
      <div className='bg-card ring-foreground/10 rounded-xl ring-1'>
        <Empty className='h-72'>
          <EmptyMedia variant='icon'>
            <ChevronRight aria-hidden='true' className='size-4' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>
              {props.searchKeyword ? '未找到匹配日志' : '暂无日志'}
            </EmptyTitle>
            <EmptyDescription>
              {props.searchKeyword
                ? '换个关键词或清除筛选条件试试'
                : '日志将出现在 API 调用或测试执行之后'}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      </div>
    )
  }

  return (
    <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
      <div className='overflow-x-auto'>
        <table className='w-full min-w-[1000px] text-[13px]'>
          <thead>
            <tr className='bg-[var(--table-header)] text-xs'>
              <th className='w-11 px-2.5 py-2'>
                <span className='flex items-center justify-center'>
                  <Checkbox
                    aria-label='全选当前页'
                    checked={allSelected}
                    onCheckedChange={props.onToggleSelectAll}
                  />
                </span>
              </th>
              <th className='w-10 px-2 py-2' />
              <th className='px-3 py-2 text-left font-medium'>
                <SortableHeader
                  sortKey='time'
                  label='时间'
                  sort={props.sort}
                  onToggleSort={() => props.onToggleSort('time')}
                />
              </th>
              <th className='px-3 py-2 text-left font-medium'>
                <SortableHeader
                  sortKey='level'
                  label='级别'
                  sort={props.sort}
                  onToggleSort={() => props.onToggleSort('level')}
                />
              </th>
              <th className='px-3 py-2 text-left font-medium'>
                <SortableHeader
                  sortKey='module'
                  label='模块'
                  sort={props.sort}
                  onToggleSort={() => props.onToggleSort('module')}
                />
              </th>
              <th className='px-3 py-2 text-left font-medium'>算法</th>
              <th className='px-3 py-2 text-left font-medium'>
                <SortableHeader
                  sortKey='source'
                  label='来源'
                  sort={props.sort}
                  onToggleSort={() => props.onToggleSort('source')}
                />
              </th>
              <th className='px-3 py-2 text-left font-medium'>内容</th>
              <th className='w-16 px-3 py-2 text-right font-medium'>操作</th>
            </tr>
          </thead>
          <tbody>
            {props.rows.map((log) => {
              const expanded = props.expandedId === log.id
              const levelKey = log.level.toUpperCase()
              const tint = LOG_LEVEL_ROW_TINT[levelKey]
              return (
                <Fragment key={log.id}>
                  <tr
                    onClick={() => props.onToggleExpand(log.id)}
                    className={cn(
                      'hover:bg-muted/40 border-border/50 cursor-pointer border-b last:border-b-0',
                      tint
                    )}
                  >
                    <td className='px-2.5 py-2' onClick={(e) => e.stopPropagation()}>
                      <span className='flex items-center justify-center'>
                        <Checkbox
                          aria-label={`选择日志 ${log.id}`}
                          checked={props.selectedIds.has(log.id)}
                          onCheckedChange={() => props.onToggleSelect(log.id)}
                        />
                      </span>
                    </td>
                    <td className='px-2 py-2'>
                      <span className='text-muted-foreground flex items-center justify-center'>
                        {expanded ? (
                          <ChevronDown aria-hidden='true' className='size-3.5' />
                        ) : (
                          <ChevronRight aria-hidden='true' className='size-3.5' />
                        )}
                      </span>
                    </td>
                    <td className='px-3 py-2 font-mono text-xs whitespace-nowrap tabular-nums'>
                      {log.time}
                    </td>
                    <td className='px-3 py-2'>
                      <StatusBadge
                        label={log.level}
                        variant={LOG_LEVEL_BADGE_VARIANT[levelKey] ?? 'neutral'}
                      />
                    </td>
                    <td className='px-3 py-2'>
                      <Badge variant='secondary'>{log.module || '—'}</Badge>
                    </td>
                    <td className='px-3 py-2'>
                      <span className='font-mono text-xs'>{log.algorithmType || '—'}</span>
                    </td>
                    <td className='px-3 py-2'>
                      <span className='text-muted-foreground text-xs'>{log.source || '—'}</span>
                    </td>
                    <td className='max-w-72 px-3 py-2'>
                      <span className='text-muted-foreground block truncate' title={log.content}>
                        {log.content}
                      </span>
                      {log.mark && (
                        <span className='bg-foreground/10 text-foreground/60 mt-0.5 inline-block rounded px-1 font-mono text-[10px]'>
                          {log.mark}
                        </span>
                      )}
                    </td>
                    <td
                      className='px-3 py-2'
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className='flex items-center justify-end gap-0.5'>
                        <MarkAction
                          log={log}
                          canManage={props.canManage}
                          onMark={props.onMark}
                        />
                        <CopyButton
                          value={formatLogCopy(log)}
                          aria-label='复制日志'
                          size='icon'
                          className='size-7'
                          iconClassName='size-3.5'
                        />
                      </div>
                    </td>
                  </tr>
                  {expanded && <LogRowDetails key={`${log.id}-detail`} log={log} />}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/**
 * 日志数据表（interfaces 层；17_配置运维.md §4.4 DataTablePage）。
 * 列=勾选/展开/时间/级别/模块/算法/来源/内容/操作；ERROR·CRITICAL 行染浅色 tint；
 * 行点击展开详情行（LogRowDetails）；行内操作「标记」（颜色 Popover，log:manage）/
 * 「复制」（CopyButton，[时间] [级别] [模块] 内容）。
 * 空态：「暂无日志」/ 搜索空「未找到匹配日志」；加载 TableSkeleton。
 */
import { ChevronDown, ChevronRight, Flag } from 'lucide-react'
import { Fragment } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { CopyButton } from '@/components/copy-button'
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
import type { LogItem } from '@/domain/models/log'
import {
  LOG_LEVEL_BADGE_VARIANT,
  LOG_LEVEL_ROW_TINT,
  LOG_MARK_COLORS,
} from '@/features/logs/constants'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { LogRowDetails } from '@/features/logs/components/log-row-details'

export type LogsTableProps = {
  rows: LogItem[]
  loading: boolean
  total: number
  searchKeyword: string
  selectedIds: Set<number>
  onToggleSelect: (id: number) => void
  onToggleSelectAll: () => void
  canManage: boolean
  expandedId: number | null
  onToggleExpand: (id: number) => void
  onMark: (log: LogItem, mark: string) => void
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
  if (!canManage) return null
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button
            variant='ghost'
            size='icon'
            className='size-7'
            aria-label={`标记日志 ${log.id}`}
          >
            <Flag aria-hidden='true' className='size-3.5' />
          </Button>
        }
      />
      <PopoverContent align='end' className='w-40 p-1.5'>
        <div className='text-muted-foreground px-2 py-1 text-xs'>选择标记颜色</div>
        <div className='grid grid-cols-2 gap-1'>
          {LOG_MARK_COLORS.map((color) => (
            <Button
              key={color.value}
              variant='ghost'
              size='sm'
              className='h-7 justify-start gap-2 text-xs'
              onClick={() => onMark(log, color.value)}
            >
              <span
                aria-hidden='true'
                className={cn('size-2.5 rounded-full', color.swatch)}
              />
              {color.label}
            </Button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}

export function LogsTable(props: LogsTableProps) {
  const isEmpty = !props.loading && props.rows.length === 0
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
              <th className='px-3 py-2 text-left font-medium'>时间</th>
              <th className='px-3 py-2 text-left font-medium'>级别</th>
              <th className='px-3 py-2 text-left font-medium'>模块</th>
              <th className='px-3 py-2 text-left font-medium'>算法</th>
              <th className='px-3 py-2 text-left font-medium'>来源</th>
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

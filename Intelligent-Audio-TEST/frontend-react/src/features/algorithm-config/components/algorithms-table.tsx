/**
 * 算法列表数据表（§3.4；DataTablePage 对位——列=勾选/ID/算法类型/名称/分组/参数数/关联用例/
 * 状态/更新时间/操作，行点击开详情，行内菜单 §3.5）。
 * 全局算法切换器联动（§2.2）：当前全局算法行标注「当前全局算法」Badge。
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
import type { AlgorithmDefinition } from '@/domain/models/algorithmConfig'
import { AlgorithmStatusBadge } from '@/features/algorithm-config/components/algorithm-status-badge'
import { AlgorithmRowActions } from '@/features/algorithm-config/components/algorithms-row-actions'

export type AlgorithmTableProps = {
  rows: AlgorithmDefinition[]
  loading: boolean
  total: number
  searchKeyword: string
  selectedIds: Set<number>
  onToggleSelect: (id: number) => void
  onToggleSelectAll: () => void
  canManage: boolean
  /** 当前全局算法 type（useAlgorithmStore），非空时高亮该行 */
  globalAlgorithmType: string
  sortOrder: 'asc' | 'desc'
  onSortChange: () => void
  onEmptyCreate: () => void
  onDetail: (algorithm: AlgorithmDefinition) => void
  onEdit: (algorithm: AlgorithmDefinition) => void
  onClone: (algorithm: AlgorithmDefinition) => void
  onDelete: (algorithm: AlgorithmDefinition) => void
}

/** 列表更新时间格式化（默认 locale；§3.1） */
function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function paramCount(algorithm: AlgorithmDefinition): number {
  return (
    algorithm.deviceParams.length +
    algorithm.apiParams.length +
    algorithm.caseParams.length
  )
}

/** 分组徽章（GroupBadge 对位；空则「—」） */
function GroupBadgeCell({ groupName }: { groupName: string | null }) {
  if (!groupName) return <span className='text-muted-foreground'>—</span>
  return (
    <span className='inline-flex h-5 max-w-32 items-center gap-1 rounded-md border border-border bg-muted/50 px-1.5 text-xs text-muted-foreground'>
      <Box aria-hidden='true' className='size-3' />
      <span className='truncate'>{groupName}</span>
    </span>
  )
}

export function AlgorithmsTable(props: AlgorithmTableProps) {
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
            <Box aria-hidden='true' className='size-4' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>
              {props.searchKeyword ? '未找到匹配的算法' : '暂无算法'}
            </EmptyTitle>
            <EmptyDescription>
              {props.searchKeyword
                ? '换个关键词或清除筛选条件试试'
                : '点击右上角「新建算法」创建第一个算法，或调整筛选条件'}
            </EmptyDescription>
          </EmptyHeader>
          {!props.searchKeyword && props.canManage && (
            <EmptyContent>
              <Button
                variant='outline'
                size='sm'
                onClick={props.onEmptyCreate}
              >
                <Box aria-hidden='true' className='size-3.5' />
                新建算法
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
        <table className='w-full min-w-[880px] text-[13px]'>
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
              <th className='px-3 py-2 text-left font-medium'>ID</th>
              <th className='px-3 py-2 text-left font-medium'>算法类型</th>
              <th className='px-3 py-2 text-left font-medium'>名称</th>
              <th className='px-3 py-2 text-left font-medium'>分组</th>
              <th className='px-3 py-2 text-right font-medium'>参数数</th>
              <th className='px-3 py-2 text-right font-medium'>关联用例</th>
              <th className='px-3 py-2 text-left font-medium'>状态</th>
              <th className='px-3 py-2 text-left font-medium'>
                <button
                  type='button'
                  onClick={props.onSortChange}
                  className='hover:text-foreground inline-flex items-center gap-1 transition-colors'
                >
                  更新时间
                  {props.sortOrder === 'desc' ? (
                    <ChevronDown aria-hidden='true' className='size-3' />
                  ) : (
                    <ChevronUp aria-hidden='true' className='size-3' />
                  )}
                </button>
              </th>
              <th className='w-14 px-3 py-2 text-right font-medium'>操作</th>
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row) => {
              const isGlobal = row.type === props.globalAlgorithmType
              return (
                <tr
                  key={row.id}
                  onClick={() => props.onDetail(row)}
                  className={cn(
                    'hover:bg-muted/40 border-border/50 cursor-pointer border-b last:border-b-0',
                    isGlobal && 'bg-primary/[0.04] dark:bg-primary/10'
                  )}
                >
                  <td className='px-2.5 py-2' onClick={(e) => e.stopPropagation()}>
                    <span className='flex items-center justify-center'>
                      <Checkbox
                        aria-label={`选择算法 ${row.name}`}
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
                  <td className='px-3 py-2'>
                    <span className='font-mono text-xs'>{row.type}</span>
                    {isGlobal && (
                      <span className='ml-2 inline-flex'>
                        <Tooltip>
                          <TooltipTrigger
                            render={
                              <Badge variant='outline' className='gap-1 px-1.5 text-[11px]'>
                                <span
                                  aria-hidden='true'
                                  className='bg-[var(--primary)] size-1.5 rounded-full'
                                />
                                当前全局算法
                              </Badge>
                            }
                          />
                          <TooltipContent>
                            与导航栏全局算法切换器联动
                          </TooltipContent>
                        </Tooltip>
                      </span>
                    )}
                  </td>
                  <td className='px-3 py-2'>
                    <span className='min-w-0 truncate font-medium' title={row.name}>
                      {row.name}
                    </span>
                  </td>
                  <td className='px-3 py-2'>
                    <GroupBadgeCell groupName={row.groupName} />
                  </td>
                  <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                    {paramCount(row)}
                  </td>
                  <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                    {row.caseCount}
                  </td>
                  <td className='px-3 py-2'>
                    <div className='flex items-center gap-1.5'>
                      <AlgorithmStatusBadge status={row.status} />
                      {/* §3.4 草稿 Badge（INT-591：后端 has_draft 字段返回后渲染） */}
                      {row.hasDraft && (
                        <Badge variant='warning' className='gap-1 px-1.5 text-[11px]'>
                          有草稿
                        </Badge>
                      )}
                    </div>
                  </td>
                  <td className='px-3 py-2 font-mono text-xs tabular-nums'>
                    {formatDateTime(row.updatedAt)}
                  </td>
                  <td
                    className='px-3 py-2'
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className='flex items-center justify-end gap-0.5'>
                      <AlgorithmRowActions
                        algorithm={row}
                        canManage={props.canManage}
                        onDetail={() => props.onDetail(row)}
                        onEdit={() => props.onEdit(row)}
                        onClone={() => props.onClone(row)}
                        onDelete={() => props.onDelete(row)}
                      />
                    </div>
                    {/* 移动端不可见计数（可访问性等价文本） */}
                    <span className='sr-only'>共 {paramCount(row)} 个参数，关联 {row.caseCount} 个用例</span>
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

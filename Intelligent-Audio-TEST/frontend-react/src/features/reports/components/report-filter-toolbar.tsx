/**
 * 报告列表工具栏（移植自 newAPI PricingToolbar，规范 §3.5）：
 * 左=计数（无筛选「共 N 个报告」/ 有筛选只留「已筛选 N 个报告」，同一数字不重复展示，
 * INT-2350）+ 全局算法联动 chip（Badge secondary + × 清空）；右=排序 DropdownMenu
 * （ArrowUpDown + Check 标记）+ 视图切换（表格/卡片）。
 */
import { ArrowUpDown, Check, LayoutGrid, Table2, X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import type {
  ReportSortBy,
  ReportSortOrder,
  ReportViewMode,
} from '@/domain/models/report'

import {
  getReportSortLabel,
  REPORT_SORT_OPTIONS,
} from '@/features/reports/constants'

interface ReportFilterToolbarProps {
  /** 当前列表命中数（服务端分页 total） */
  filteredCount: number
  /** 当前筛选口径下的全量计数（GET /reports/tab-counts 的 all，无筛选时与 filteredCount 相等） */
  totalCount: number
  /** 是否处于筛选/视图收窄态：有筛选时只留「已筛选 N」，不再重复写「共 N」 */
  hasActiveFilters: boolean
  sortBy: ReportSortBy
  sortOrder: ReportSortOrder
  onSortChange: (sortBy: ReportSortBy, sortOrder?: ReportSortOrder) => void
  viewMode: ReportViewMode
  onViewModeChange: (view: ReportViewMode) => void
  /** 全局算法联动 chip 文案（undefined 时不渲染） */
  linkedAlgorithm?: string
  onClearAlgorithm?: () => void
}

export function ReportFilterToolbar({
  filteredCount,
  totalCount,
  hasActiveFilters,
  sortBy,
  sortOrder,
  onSortChange,
  viewMode,
  onViewModeChange,
  linkedAlgorithm,
  onClearAlgorithm,
}: ReportFilterToolbarProps) {
  return (
    <div className='bg-card rounded-xl border p-3'>
      <div className='flex flex-wrap items-center justify-between gap-3'>
        <div className='text-muted-foreground flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-2 text-sm'>
          {/* INT-2350：有筛选只展示一个数字（已筛选 N），无筛选展示全量（共 N），不重复同一计数 */}
          {hasActiveFilters ? (
            <span className='flex items-baseline gap-1'>
              已筛选{' '}
              <span className='text-foreground font-semibold tabular-nums'>
                {filteredCount}
              </span>{' '}
              个报告
            </span>
          ) : (
            <span className='flex items-baseline gap-1'>
              共{' '}
              <span className='text-foreground font-semibold tabular-nums'>{totalCount}</span>{' '}
              个报告
            </span>
          )}
          {linkedAlgorithm && (
            <Badge variant='secondary' className='h-6 gap-1 px-2'>
              算法：{linkedAlgorithm}
              <button
                type='button'
                aria-label='清除算法联动筛选'
                onClick={onClearAlgorithm}
                className='text-muted-foreground hover:text-foreground rounded-sm outline-none transition-colors'
              >
                <X className='size-3' />
              </button>
            </Badge>
          )}
        </div>

        <div className='flex min-w-0 flex-wrap items-center gap-2'>
          <DropdownMenu modal={false}>
            <DropdownMenuTrigger
              render={
                <Button variant='outline' size='sm' className='h-8 gap-1.5 px-3 text-xs' />
              }
            >
              <ArrowUpDown className='size-3.5' />
              {getReportSortLabel(sortBy)}
              <span className='text-muted-foreground/60'>
                {sortOrder === 'asc' ? '↑' : '↓'}
              </span>
            </DropdownMenuTrigger>
            <DropdownMenuContent align='end' className='w-44'>
              {REPORT_SORT_OPTIONS.map((option) => {
                const active = sortBy === option.value
                return (
                  <DropdownMenuItem
                    key={option.value}
                    className='gap-2'
                    onClick={() => onSortChange(option.value)}
                  >
                    <Check
                      className={cn('size-4 shrink-0', active ? 'opacity-100' : 'opacity-0')}
                    />
                    {option.label}
                    {active && (
                      <span
                        className='text-muted-foreground ml-auto text-xs'
                        onClick={(event) => {
                          event.stopPropagation()
                          onSortChange(option.value, sortOrder === 'asc' ? 'desc' : 'asc')
                        }}
                      >
                        {sortOrder === 'asc' ? '升序' : '降序'}
                      </span>
                    )}
                  </DropdownMenuItem>
                )
              })}
              <DropdownMenuSeparator />
              <div className='text-muted-foreground px-1.5 py-1 text-xs'>
                再次点击排序项切换升降序
              </div>
            </DropdownMenuContent>
          </DropdownMenu>

          <div
            role='group'
            aria-label='视图切换'
            className='bg-muted/60 inline-flex h-8 items-center rounded-lg border p-0.5'
          >
            <Button
              variant={viewMode === 'table' ? 'default' : 'ghost'}
              size='icon-sm'
              className='h-full w-7'
              aria-pressed={viewMode === 'table'}
              aria-label='表格视图'
              onClick={() => onViewModeChange('table')}
            >
              <Table2 className='size-3.5' />
            </Button>
            <Button
              variant={viewMode === 'card' ? 'default' : 'ghost'}
              size='icon-sm'
              className='h-full w-7'
              aria-pressed={viewMode === 'card'}
              aria-label='卡片视图'
              onClick={() => onViewModeChange('card')}
            >
              <LayoutGrid className='size-3.5' />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

/**
 * 报告展示页工具栏（15_报告域.md §2.1：PricingToolbar 同款裁剪）。
 * 「共 {n} 个已发布报告」+ 排序 DropdownMenu（创建时间/报告名称/通过率/用例数）
 * + 表格/卡片视图切换。本页不渲染全局算法联动 chip（INT-442：算法切换已由「当前算法」大卡承载）。
 */
import { ArrowDownAZ, ArrowUpAZ, ChevronDown, LayoutGrid, List, X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { ReportSortBy, ReportSortOrder, ReportViewMode } from '@/domain/models/report'
import { cn } from '@/lib/utils'

import { REPORT_SORT_OPTIONS } from '@/features/reports/constants'

interface ReportShowcaseToolbarProps {
  filteredCount: number
  sortBy: ReportSortBy
  sortOrder: ReportSortOrder
  onSortChange: (sortBy: ReportSortBy, sortOrder?: ReportSortOrder) => void
  viewMode: ReportViewMode
  onViewModeChange: (view: ReportViewMode) => void
  /** 当前算法筛选（大卡写回全局 store 后列表附 algorithm_type；chip 展示用） */
  algorithmLabel?: string
  onClearAlgorithm?: () => void
}

export function ReportShowcaseToolbar({
  filteredCount,
  sortBy,
  sortOrder,
  onSortChange,
  viewMode,
  onViewModeChange,
  algorithmLabel,
  onClearAlgorithm,
}: ReportShowcaseToolbarProps) {
  const currentSort = REPORT_SORT_OPTIONS.find((o) => o.value === sortBy)
  return (
    <div className='flex flex-wrap items-center justify-between gap-2'>
      <div className='flex flex-wrap items-center gap-2'>
        <span className='text-muted-foreground tabular-nums text-sm'>
          共 {filteredCount} 个已发布报告
        </span>
        {algorithmLabel && (
          <Badge variant='secondary' className='gap-1.5'>
            算法：{algorithmLabel}
            {onClearAlgorithm && (
              <button
                type='button'
                aria-label='清除算法筛选'
                className='hover:text-foreground text-muted-foreground transition-colors'
                onClick={onClearAlgorithm}
              >
                <X aria-hidden='true' className='size-3' />
              </button>
            )}
          </Badge>
        )}
      </div>

      <div className='flex items-center gap-1.5'>
        <DropdownMenu modal={false}>
          <DropdownMenuTrigger
            render={
              <Button
                variant='outline'
                size='sm'
                className='h-8 gap-1.5 px-2.5 font-normal'
                aria-label='排序'
              />
            }
          >
            {sortOrder === 'asc' ? (
              <ArrowUpAZ aria-hidden='true' className='size-3.5' />
            ) : (
              <ArrowDownAZ aria-hidden='true' className='size-3.5' />
            )}
            {currentSort?.label ?? '创建时间'}
            <ChevronDown aria-hidden='true' className='size-3.5 opacity-60' />
          </DropdownMenuTrigger>
          <DropdownMenuContent align='end' className='w-44'>
            {REPORT_SORT_OPTIONS.map((option) => (
              <DropdownMenuItem
                key={option.value}
                onClick={() => onSortChange(option.value)}
              >
                {option.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <div className='bg-muted flex items-center rounded-lg p-0.5'>
          <button
            type='button'
            className={cn(
              'flex h-7 w-7 items-center justify-center rounded-md transition-colors',
              viewMode === 'table' ? 'bg-background shadow-sm' : 'text-muted-foreground'
            )}
            aria-label='表格视图'
            onClick={() => onViewModeChange('table')}
          >
            <List aria-hidden='true' className='size-4' />
          </button>
          <button
            type='button'
            className={cn(
              'flex h-7 w-7 items-center justify-center rounded-md transition-colors',
              viewMode === 'card' ? 'bg-background shadow-sm' : 'text-muted-foreground'
            )}
            aria-label='卡片视图'
            onClick={() => onViewModeChange('card')}
          >
            <LayoutGrid aria-hidden='true' className='size-4' />
          </button>
        </div>
      </div>
    </div>
  )
}

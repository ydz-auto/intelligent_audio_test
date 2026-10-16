/**
 * 报告中心 Hero 头（移植自 newAPI pricing-hero 版式，规范 §3.4/§3.5）：
 * Badge eyebrow + h1 + 说明 + SearchBar（右）+ 报告类型 chips + 状态/时间筛选组 + 清除筛选。
 * 口径修正 2026-10-16：类型/状态均为筛选条件（chips 常驻、默认「全部」），非页面层级。
 */
import { CalendarDays, SlidersHorizontal } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type {
  ReportStatus,
  ReportTimeRange,
  ReportType,
} from '@/domain/models/report'
import { cn } from '@/lib/utils'

import {
  REPORT_STATUS_OPTIONS,
  REPORT_TYPE_OPTIONS,
  TIME_RANGE_OPTIONS,
} from '@/features/reports/constants'
import { SearchBar } from './search-bar'

interface ReportHeroProps {
  totalReports: number
  draftCount: number
  publishedCount: number
  typeCounts: Record<ReportType | 'all', number>
  search: string
  onSearchChange: (value: string) => void
  type?: ReportType
  onTypeChange: (value?: ReportType) => void
  status?: ReportStatus
  onStatusChange: (value?: ReportStatus) => void
  timeRange?: ReportTimeRange
  onTimeRangeChange: (value?: ReportTimeRange) => void
  startTime?: string
  endTime?: string
  onCustomRangeChange: (start?: string, end?: string) => void
  hasActiveFilters: boolean
  onClearAll: () => void
}

export function ReportHero({
  totalReports,
  draftCount,
  publishedCount,
  typeCounts,
  search,
  onSearchChange,
  type,
  onTypeChange,
  status,
  onStatusChange,
  timeRange,
  onTimeRangeChange,
  startTime,
  endTime,
  onCustomRangeChange,
  hasActiveFilters,
  onClearAll,
}: ReportHeroProps) {
  return (
    <header className='pricing-hero mb-6 rounded-3xl border px-6 py-8 sm:px-8 sm:py-10'>
      <div className='grid gap-7 lg:grid-cols-[1.1fr_0.9fr] lg:items-center'>
        <div>
          <Badge variant='outline' className='mb-4'>
            报告中心
          </Badge>
          <h1 className='max-w-2xl text-3xl leading-tight font-semibold tracking-tight sm:text-4xl'>
            浏览测试报告，按任务与算法检索
          </h1>
          <p className='text-muted-foreground mt-4 text-sm leading-7'>
            共 {totalReports} 个报告，其中草稿 {draftCount} 个、已发布 {publishedCount} 个
          </p>
        </div>
        <div>
          <SearchBar
            value={search}
            onChange={onSearchChange}
            onClear={() => onSearchChange('')}
            placeholder='搜索报告名称、任务或算法...'
          />
          <p className='text-muted-foreground mt-3 text-xs leading-6'>
            报告为任务执行结果的落库快照，支持对比、导出与发布。
          </p>
        </div>
      </div>

      <nav
        aria-label='报告类型筛选'
        className='mt-8 flex flex-wrap gap-2 border-t pt-6'
      >
        {REPORT_TYPE_OPTIONS.map((option) => {
          const active = type === undefined
            ? option.value === 'all'
            : option.value === type
          const count = typeCounts[option.value as ReportType | 'all'] ?? 0
          return (
            <Button
              key={option.value}
              variant={active ? 'default' : 'outline'}
              aria-pressed={active}
              className='h-11 gap-2 rounded-xl px-4'
              onClick={() =>
                onTypeChange(
                  option.value === 'all' ? undefined : (option.value as ReportType)
                )
              }
            >
              {option.label}
              <span className='opacity-70'>{count}</span>
            </Button>
          )
        })}
      </nav>

      <div className='mt-4 flex flex-wrap items-center gap-2'>
        <SlidersHorizontal className='text-muted-foreground size-4' aria-hidden='true' />
        {/* 状态筛选（PricingCapabilityFilter 单筛 chips 形态） */}
        <div role='group' aria-label='报告状态筛选' className='flex flex-wrap items-center gap-2'>
          {REPORT_STATUS_OPTIONS.map((option) => {
            const active =
              option.value === 'all' ? status === undefined : status === option.value
            return (
              <Button
                key={option.value}
                variant={active ? 'default' : 'outline'}
                aria-pressed={active}
                className='h-9 gap-2 rounded-xl px-4'
                onClick={() =>
                  onStatusChange(
                    option.value === 'all' ? undefined : (option.value as ReportStatus)
                  )
                }
              >
                {option.label}
              </Button>
            )
          })}
        </div>

        {/* 时间范围 */}
        <Select
          value={timeRange ?? 'all'}
          onValueChange={(v) => onTimeRangeChange(v === 'all' ? undefined : (v as ReportTimeRange))}
        >
          <SelectTrigger size='sm' aria-label='时间范围'>
            <CalendarDays className='text-muted-foreground size-4' />
            <SelectValue />
          </SelectTrigger>
          <SelectContent align='start'>
            {TIME_RANGE_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {timeRange === 'custom' && (
          <div className='flex flex-wrap items-center gap-2'>
            <Input
              type='datetime-local'
              value={startTime ?? ''}
              onChange={(event) => onCustomRangeChange(event.target.value, endTime)}
              aria-label='开始时间'
              className='h-8 w-[190px] text-sm tabular-nums'
            />
            <span className='text-muted-foreground text-xs'>至</span>
            <Input
              type='datetime-local'
              value={endTime ?? ''}
              onChange={(event) => onCustomRangeChange(startTime, event.target.value)}
              aria-label='结束时间'
              className='h-8 w-[190px] text-sm tabular-nums'
            />
          </div>
        )}

        {hasActiveFilters && (
          <Button variant='outline' size='sm' onClick={onClearAll} className={cn('h-8')}>
            清除全部筛选
          </Button>
        )}
      </div>
    </header>
  )
}

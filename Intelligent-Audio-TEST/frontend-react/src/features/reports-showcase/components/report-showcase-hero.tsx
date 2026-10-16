/**
 * 报告展示页 Hero 头（15_报告域.md §2.1 INT-441：pricing-hero 版式偏展示裁剪）。
 * Badge「报告」+ h1「浏览测试报告」+ SearchBar「搜索报告名称、任务或算法...」
 * + 报告类型 chips（h-11 rounded-xl）+ 时间范围筛选（状态固定已发布，不设状态筛选）。
 */
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { ReportTimeRange, ReportType } from '@/domain/models/report'
import { cn } from '@/lib/utils'

import { SearchBar } from '@/features/reports/components/search-bar'

const TYPE_CHIPS: { value: ReportType | 'all'; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'task', label: '任务报告' },
  { value: 'comparison', label: '对比报告' },
  { value: 'secondary_comparison', label: '二次对比报告' },
]

const TIME_RANGE_OPTIONS: { value: ReportTimeRange | 'all'; label: string }[] = [
  { value: 'all', label: '全部时间' },
  { value: 'today', label: '今日' },
  { value: 'yesterday', label: '昨日' },
  { value: 'week', label: '近7天' },
  { value: 'month', label: '近30天' },
  { value: 'custom', label: '自定义' },
]

interface ReportShowcaseHeroProps {
  search: string
  onSearchChange: (value: string) => void
  type: ReportType | undefined
  onTypeChange: (value: ReportType | undefined) => void
  timeRange: ReportTimeRange | undefined
  onTimeRangeChange: (value: ReportTimeRange | undefined) => void
  startTime?: string
  endTime?: string
  onCustomRangeChange: (start?: string, end?: string) => void
  hasActiveFilters: boolean
  onClearAll: () => void
}

export function ReportShowcaseHero({
  search,
  onSearchChange,
  type,
  onTypeChange,
  timeRange,
  onTimeRangeChange,
  startTime,
  endTime,
  onCustomRangeChange,
  hasActiveFilters,
  onClearAll,
}: ReportShowcaseHeroProps) {
  return (
    <div className='rounded-3xl border px-6 py-8'>
      <div className='flex flex-wrap items-center gap-2'>
        <Badge variant='outline'>报告</Badge>
        {timeRange && (
          <Badge variant='secondary'>{timeRange === 'custom' ? '自定义时间' : timeRange}</Badge>
        )}
        {hasActiveFilters && (
          <button
            type='button'
            onClick={onClearAll}
            className='text-muted-foreground hover:text-foreground text-xs transition-colors'
          >
            清除全部筛选
          </button>
        )}
      </div>

      <div className='mt-4 flex flex-wrap items-end justify-between gap-4'>
        <div>
          <h1 className='text-3xl font-bold tracking-tight sm:text-4xl'>
            浏览测试报告
          </h1>
          <p className='text-muted-foreground mt-2 max-w-2xl text-sm leading-relaxed'>
            展示已发布的测试报告成果，支持按类型、时间与算法检索；行内可查看详情或复制分享链接。
          </p>
        </div>
        <SearchBar
          value={search}
          onChange={onSearchChange}
          onClear={() => onSearchChange('')}
          placeholder='搜索报告名称、任务或算法...'
          className='w-full sm:w-80'
        />
      </div>

      <div className='mt-5 flex flex-wrap items-center gap-2'>
        <div className='flex flex-wrap gap-1.5'>
          {TYPE_CHIPS.map((chip) => {
            const active = type === undefined ? chip.value === 'all' : type === chip.value
            return (
              <button
                key={chip.value}
                type='button'
                className={cn(
                  'h-11 rounded-xl px-4 text-sm font-medium transition-colors',
                  active
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-muted text-muted-foreground'
                )}
                onClick={() => onTypeChange(chip.value === 'all' ? undefined : chip.value)}
              >
                {chip.label}
              </button>
            )
          })}
          <span
            className='bg-muted text-muted-foreground inline-flex h-11 items-center gap-1.5 rounded-xl px-4 text-sm font-medium'
            title='本页仅展示已发布报告'
          >
            <span aria-hidden='true' className='bg-success size-2 rounded-full' />
            已发布
          </span>
        </div>
        <Select
          value={timeRange ?? 'all'}
          onValueChange={(value) =>
            onTimeRangeChange(value === 'all' ? undefined : (value as ReportTimeRange))
          }
        >
          <SelectTrigger className='h-11 w-36'>
            <SelectValue placeholder='全部时间' />
          </SelectTrigger>
          <SelectContent>
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
              className='h-9 w-[190px] text-sm tabular-nums'
            />
            <span className='text-muted-foreground text-xs'>至</span>
            <Input
              type='datetime-local'
              value={endTime ?? ''}
              onChange={(event) => onCustomRangeChange(startTime, event.target.value)}
              aria-label='结束时间'
              className='h-9 w-[190px] text-sm tabular-nums'
            />
          </div>
        )}
      </div>
    </div>
  )
}

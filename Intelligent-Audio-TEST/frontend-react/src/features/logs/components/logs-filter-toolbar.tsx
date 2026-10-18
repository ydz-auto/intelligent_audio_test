/**
 * 日志筛选工具栏（features/logs；17_配置运维.md §4.2，照 newAPI common-logs-filter-bar
 * / logs-filter-toolbar 移植）。
 * 主筛选（日期范围/搜索/分类/模块/标记/算法）+ 级别 tag 多选 + 高级过滤折叠 + 右端搜索/重置；
 * 移动端折叠进 Sheet（max-h-[85dvh]），mobileFilterCount 徽标。
 */
import { ChevronDown, FilterX, Search, SlidersHorizontal } from 'lucide-react'
import { useMemo, useState } from 'react'

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
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  LOG_CATEGORY_OPTIONS,
  LOG_LEVELS,
  LOG_MARK_OPTIONS,
  LOG_MODULE_OPTIONS,
} from '@/domain/models/log'
import { FILTER_ALL } from '@/features/logs/constants'
import type {
  LogAdvancedState,
  LogFilterState,
} from '@/features/logs/types'
import { cn } from '@/lib/utils'

export type LogsFilterToolbarProps = {
  searchValue: string
  onSearchChange: (value: string) => void
  onSearch: () => void
  searchLoading: boolean
  filters: LogFilterState
  onFilterChange: (patch: Partial<LogFilterState>) => void
  selectedLevels: string[]
  onToggleLevel: (level: string) => void
  advanced: LogAdvancedState
  onAdvancedChange: (patch: Partial<LogAdvancedState>) => void
  algorithmOptions: { value: string; label: string }[]
  onReset: () => void
  hasActiveFilters: boolean
}

/** 紧凑日期范围（§4.2 CompactDateTimeRangePicker 对位；datetime-local 原生值透传后端） */
function DateRangeInputs({
  startTime,
  endTime,
  onChange,
}: {
  startTime: string
  endTime: string
  onChange: (patch: Partial<LogFilterState>) => void
}) {
  return (
    <div className='flex items-center gap-1'>
      <Input
        type='datetime-local'
        aria-label='开始时间'
        className='h-8 min-w-0 text-sm leading-5'
        value={startTime}
        onChange={(event) => onChange({ startTime: event.target.value })}
      />
      <span className='text-muted-foreground px-0.5 text-xs'>至</span>
      <Input
        type='datetime-local'
        aria-label='结束时间'
        className='h-8 min-w-0 text-sm leading-5'
        value={endTime}
        onChange={(event) => onChange({ endTime: event.target.value })}
      />
    </div>
  )
}

export function LogsFilterToolbar(props: LogsFilterToolbarProps) {
  const {
    searchValue,
    onSearchChange,
    onSearch,
    searchLoading,
    filters,
    onFilterChange,
    selectedLevels,
    onToggleLevel,
    advanced,
    onAdvancedChange,
    algorithmOptions,
    onReset,
    hasActiveFilters,
  } = props

  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  const mobileFilterCount = useMemo(() => {
    let count = 0
    if (filters.startTime || filters.endTime) count += 1
    if (filters.category !== FILTER_ALL) count += 1
    if (filters.module !== FILTER_ALL) count += 1
    if (filters.mark !== FILTER_ALL) count += 1
    if (filters.algorithmType !== FILTER_ALL) count += 1
    if (selectedLevels.length > 0 && selectedLevels.length < LOG_LEVELS.length) count += 1
    if (Object.values(advanced).some((v) => v !== '')) count += 1
    return count
  }, [filters, selectedLevels, advanced])

  /** 主筛选行（桌面网格 + 移动端共用） */
  const primaryFilters = (
    <div className='grid min-w-0 flex-1 grid-cols-1 gap-2 sm:grid-cols-[repeat(auto-fit,minmax(10rem,1fr))]'>
      <div className='sm:col-span-2'>
        <DateRangeInputs
          startTime={filters.startTime}
          endTime={filters.endTime}
          onChange={onFilterChange}
        />
      </div>
      <div className='relative'>
        <Search
          aria-hidden='true'
          className='text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2'
        />
        <Input
          autoComplete='off'
          placeholder='搜索日志内容...'
          aria-label='搜索日志内容'
          className='h-8 min-w-0 pl-8 text-sm leading-5'
          value={searchValue}
          onChange={(event) => onSearchChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') onSearch()
          }}
        />
      </div>
      <Select
        value={filters.category}
        onValueChange={(value) => onFilterChange({ category: value ?? FILTER_ALL })}
      >
        <SelectTrigger size='sm' aria-label='分类'>
          <SelectValue>
            {filters.category === FILTER_ALL
              ? '所有分类'
              : (LOG_CATEGORY_OPTIONS.find((option) => option.value === filters.category)?.label ?? '所有分类')}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value='all'>所有分类</SelectItem>
          {LOG_CATEGORY_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select
        value={filters.module}
        onValueChange={(value) => onFilterChange({ module: value ?? FILTER_ALL })}
      >
        <SelectTrigger size='sm' aria-label='模块'>
          <SelectValue>
            {filters.module === FILTER_ALL
              ? '所有模块'
              : (LOG_MODULE_OPTIONS.find((option) => option.value === filters.module)?.label ?? '所有模块')}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value='all'>所有模块</SelectItem>
          {LOG_MODULE_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select
        value={filters.mark}
        onValueChange={(value) => onFilterChange({ mark: value ?? FILTER_ALL })}
      >
        <SelectTrigger size='sm' aria-label='标记'>
          <SelectValue>
            {filters.mark === FILTER_ALL
              ? '所有标记'
              : (LOG_MARK_OPTIONS.find((option) => option.value === filters.mark)?.label ?? '所有标记')}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value='all'>所有标记</SelectItem>
          {LOG_MARK_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select
        value={filters.algorithmType}
        onValueChange={(value) => onFilterChange({ algorithmType: value ?? FILTER_ALL })}
      >
        <SelectTrigger size='sm' aria-label='算法类型'>
          <SelectValue>
            {filters.algorithmType === FILTER_ALL
              ? '全部算法'
              : (algorithmOptions.find((option) => option.value === filters.algorithmType)?.label ?? '全部算法')}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value='all'>全部算法</SelectItem>
          {algorithmOptions.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )

  /** 高级过滤折叠区 */
  const advancedFilters = (
    <div className='grid min-w-0 flex-1 grid-cols-1 gap-2 sm:grid-cols-[repeat(auto-fit,minmax(10rem,1fr))]'>
      <Input
        className='h-8 min-w-0 text-sm leading-5'
        placeholder='设备ID'
        aria-label='设备ID'
        value={advanced.deviceId}
        onChange={(event) => onAdvancedChange({ deviceId: event.target.value })}
      />
      <Input
        className='h-8 min-w-0 text-sm leading-5'
        placeholder='任务ID'
        aria-label='任务ID'
        value={advanced.taskId}
        onChange={(event) => onAdvancedChange({ taskId: event.target.value })}
      />
      <Input
        className='h-8 min-w-0 text-sm leading-5'
        placeholder='评估ID或轮次'
        aria-label='评估ID或轮次'
        value={advanced.evaluationId}
        onChange={(event) => onAdvancedChange({ evaluationId: event.target.value })}
      />
      {/* 用户ID过滤后端 LogListQuery 无 user_id（INT-763 代码审计 P3，FEAT INT-806）：
          落地前置灰 + Tooltip，避免用户以为已过滤（与「仅自己」Tab 同口径） */}
      <TooltipProvider delay={100}>
        <Tooltip>
          <TooltipTrigger
            render={
              <span className='inline-flex'>
                <Input
                  className='h-8 min-w-0 text-sm leading-5'
                  placeholder='用户ID'
                  aria-label='用户ID'
                  value={advanced.userId}
                  disabled
                />
              </span>
            }
          />
          <TooltipContent>用户ID过滤待后端接口（FEAT INT-806）落地</TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <Input
        className='h-8 min-w-0 text-sm leading-5'
        placeholder='线程ID'
        aria-label='线程ID'
        value={advanced.threadId}
        onChange={(event) => onAdvancedChange({ threadId: event.target.value })}
      />
      <Input
        className='h-8 min-w-0 text-sm leading-5'
        placeholder='内容包含'
        aria-label='日志内容包含'
        value={advanced.contentInclude}
        onChange={(event) => onAdvancedChange({ contentInclude: event.target.value })}
      />
      <Input
        className='h-8 min-w-0 text-sm leading-5'
        placeholder='内容不包含'
        aria-label='日志内容不包含'
        value={advanced.contentExclude}
        onChange={(event) => onAdvancedChange({ contentExclude: event.target.value })}
      />
    </div>
  )

  const filterBody = (
    <div className='flex flex-col gap-2.5'>
      {primaryFilters}
      {/* 级别 tag 多选（§4.2 levelFilters：选中 primary，可单个移除 ×） */}
      <div className='flex flex-wrap items-center gap-1.5'>
        <span className='text-muted-foreground text-xs'>日志级别</span>
        {LOG_LEVELS.map((level) => {
          const selected = selectedLevels.includes(level)
          return (
            <button
              key={level}
              type='button'
              aria-pressed={selected}
              onClick={() => onToggleLevel(level)}
              className={cn(
                'inline-flex h-6 items-center gap-1 rounded-full px-2 text-xs font-medium transition-colors',
                selected
                  ? 'bg-primary text-primary-foreground'
                  : 'border-border/60 bg-muted/30 hover:bg-muted text-muted-foreground border'
              )}
            >
              {level}
              {selected && (
                <span aria-hidden='true' className='text-primary-foreground/70 text-sm leading-none'>
                  ×
                </span>
              )}
            </button>
          )
        })}
      </div>
      {/* 高级过滤折叠（§4.2 advancedFilters） */}
      <div className='flex flex-wrap items-center justify-between gap-1.5'>
        <Button
          type='button'
          variant='ghost'
          size='sm'
          aria-expanded={advancedOpen}
          className='text-primary h-8 gap-1 px-2.5'
          onClick={() => setAdvancedOpen((v) => !v)}
        >
          <SlidersHorizontal aria-hidden='true' className='size-3.5' />
          {advancedOpen ? '收起高级过滤' : '高级过滤'}
          <ChevronDown
            aria-hidden='true'
            className={cn('size-3.5 transition-transform', advancedOpen && 'rotate-180')}
          />
        </Button>
      </div>
      {advancedOpen && (
        <div className='border-border/60 rounded-lg border p-2.5'>{advancedFilters}</div>
      )}
      {/* 右端：搜索 / 重置 */}
      <div className='flex flex-wrap items-center gap-1.5'>
        <div className='ml-auto flex flex-wrap items-center gap-1.5'>
          {hasActiveFilters && (
            <Button
              variant='ghost'
              size='sm'
              className='h-8 gap-1 px-2.5'
              onClick={onReset}
            >
              <FilterX aria-hidden='true' className='size-3.5' />
              重置
            </Button>
          )}
          <Button
            size='sm'
            className='h-8 gap-1.5 px-2.5'
            disabled={searchLoading}
            onClick={onSearch}
          >
            <Search aria-hidden='true' className='size-3.5' />
            搜索
          </Button>
        </div>
      </div>
    </div>
  )

  return (
    <div className='border-border/60 bg-card/50 rounded-lg border p-2.5 sm:p-3'>
      {/* 桌面：直接展示 */}
      <div className='hidden sm:block'>{filterBody}</div>
      {/* 移动端：折叠进 Sheet */}
      <div className='sm:hidden'>
        <div className='flex items-center gap-2'>
          <Button
            variant='outline'
            size='sm'
            className='h-8 flex-1 justify-start gap-2 px-2.5'
            onClick={() => setMobileOpen(true)}
          >
            <SlidersHorizontal aria-hidden='true' className='size-3.5' />
            筛选
            {mobileFilterCount > 0 && (
              <Badge className='text-primary bg-primary/10 ml-auto inline-flex size-5 items-center justify-center rounded-full text-[11px] font-semibold tabular-nums'>
                {mobileFilterCount}
              </Badge>
            )}
          </Button>
          <Button
            size='sm'
            className='h-8 gap-1.5 px-2.5'
            disabled={searchLoading}
            onClick={onSearch}
          >
            <Search aria-hidden='true' className='size-3.5' />
            搜索
          </Button>
        </div>
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetContent side='bottom' showCloseButton className='max-h-[85dvh] overflow-y-auto'>
            <SheetHeader>
              <SheetTitle>日志筛选</SheetTitle>
              <SheetDescription>按条件筛选日志</SheetDescription>
            </SheetHeader>
            <div className='pt-2'>{filterBody}</div>
          </SheetContent>
        </Sheet>
      </div>
    </div>
  )
}

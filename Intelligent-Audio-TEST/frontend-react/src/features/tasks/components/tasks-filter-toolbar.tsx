/**
 * 任务筛选工具栏（09_任务域.md §3.5，LogsFilterToolbar 形态：
 * `bg-card/50 rounded-lg border p-2.5 sm:p-3` 容器；三行结构——
 * 筛选行（primaryFilters 网格）→ stats 徽章行 + 动作行 → 高级筛选展开区）。
 * 表单模式：点「查询」才提交（onSearch 显式查询，对齐 usage-logs 行为）。
 * 页签裁剪：评估状态仅日常；任务类型/发布状态仅已发布；合并状态仅合并。
 */
import {
  CalendarDays,
  Check,
  ChevronDown,
  FilterX,
  Search,
  SlidersHorizontal,
} from 'lucide-react'
import { useCallback, useRef, useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import type { TaskListFilters } from '@/application/tasks/use-tasks-list'
import {
  EVALUATION_STATUS_OPTIONS,
  EXECUTION_STATUS_OPTIONS,
  MERGE_STATUS_OPTIONS,
  PUBLISHED_STATUS_OPTIONS,
  PUBLISHED_TYPE_OPTIONS,
  TASK_TAG_OPTIONS,
  TIME_RANGE_OPTIONS,
  type TasksTabKey,
} from '@/features/tasks/constants'
import { FavoriteTrashToggle } from '@/features/tasks/components/favorite-trash-toggle'
import { GlobalAlgorithmChip } from '@/features/tasks/components/global-algorithm-chip'
import { TasksStatsRow } from '@/features/tasks/components/tasks-stats-row'

export interface TasksFilterToolbarProps {
  tab: TasksTabKey
  filters: TaskListFilters
  onChange: (next: TaskListFilters) => void
  onReset: () => void
  onSearch: () => void
  isFiltered: boolean
}

/** 单选 facet chip（Popover + 选项列表 + 选中态） */
function SingleFacet({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string | null | undefined
  options: Array<{ value: string; label: string }>
  onChange: (value: string | null) => void
}) {
  const current = options.find((o) => o.value === value)
  const [open, setOpen] = useState(false)
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant='outline'
            size='sm'
            className='h-8 gap-1.5 px-2.5 font-normal'
          />
        }
      >
        <span className='text-muted-foreground'>{label}</span>
        <span className='max-w-28 truncate font-medium'>
          {current?.label ?? '全部'}
        </span>
        <ChevronDown
          aria-hidden='true'
          className={cn('size-3.5 transition-transform', open && 'rotate-180')}
        />
      </PopoverTrigger>
      <PopoverContent align='start' className='min-w-48 p-1.5'>
        {options.map((option) => (
          <button
            key={option.value}
            type='button'
            onClick={() => {
              onChange(option.value === value ? null : option.value)
              setOpen(false)
            }}
            className={cn(
              'hover:bg-accent flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-start text-sm transition-colors',
              option.value === value && 'bg-accent'
            )}
          >
            {option.label}
            {option.value === value && (
              <Check aria-hidden='true' className='size-4 shrink-0' />
            )}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  )
}

/** 多选 facet chip（标签；Popover + Checkbox + 计数） */
function MultiFacet({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string[]
  options: string[]
  onChange: (value: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const activeCount = value.length
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant='outline'
            size='sm'
            className='h-8 gap-1.5 px-2.5 font-normal'
          />
        }
      >
        <span className='text-muted-foreground'>{label}</span>
        {activeCount > 0 ? (
          <Badge className='rounded-sm px-1 font-normal'>{activeCount}</Badge>
        ) : (
          <span className='max-w-28 truncate font-medium'>全部</span>
        )}
        <ChevronDown
          aria-hidden='true'
          className={cn('size-3.5 transition-transform', open && 'rotate-180')}
        />
      </PopoverTrigger>
      <PopoverContent align='start' className='max-w-72 min-w-52 p-1.5'>
        {options.length === 0 ? (
          <p className='text-muted-foreground px-3 py-4 text-center text-sm'>
            暂无标签
          </p>
        ) : (
          <>
            <div className='border-border/60 mb-1 flex max-h-56 flex-col gap-0.5 overflow-y-auto'>
              {options.map((option) => {
                const checked = value.includes(option)
                return (
                  <label
                    key={option}
                    className='hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors'
                  >
                    <Checkbox
                      checked={checked}
                      onCheckedChange={() =>
                        onChange(
                          checked
                            ? value.filter((v) => v !== option)
                            : [...value, option]
                        )
                      }
                    />
                    <span className='min-w-0 flex-1 truncate'>{option}</span>
                  </label>
                )
              })}
            </div>
            <div className='border-t pt-1'>
              <button
                type='button'
                className='text-muted-foreground hover:text-foreground text-xs font-medium transition-colors'
                onClick={() => onChange([])}
              >
                清空选择
              </button>
            </div>
          </>
        )}
      </PopoverContent>
    </Popover>
  )
}

/** 简易 Select 封装（h-8，timeRange 用） */
function SelectFilter({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: Array<{ value: string; label: string }>
  onChange: (value: string) => void
}) {
  return (
    <Select value={value} onValueChange={(next) => onChange(next ?? '')}>
      <SelectTrigger size='sm' className='h-8 gap-1.5 px-2.5' aria-label={label}>
        <SelectValue>{options.find((o) => o.value === value)?.label ?? label}</SelectValue>
      </SelectTrigger>
      <SelectContent align='start'>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function TasksFilterToolbar({
  tab,
  filters,
  onChange,
  onReset,
  onSearch,
  isFiltered,
}: TasksFilterToolbarProps) {
  const { hasPermission } = usePermissions()
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)
  const [searchInput, setSearchInput] = useState(filters.search ?? '')

  const update = useCallback(
    (patch: Partial<TaskListFilters>) => onChange({ ...filters, ...patch }),
    [filters, onChange]
  )

  /** 搜索 debounce 500ms（users 表同款） */
  const debounceTimer = useRef<number | null>(null)
  const handleSearchChange = (value: string) => {
    setSearchInput(value)
    if (debounceTimer.current) window.clearTimeout(debounceTimer.current)
    debounceTimer.current = window.setTimeout(() => {
      update({ search: value.trim() })
    }, 500)
  }

  const isDaily = tab === 'daily'
  const isPublished = tab === 'published'
  const isMerged = tab === 'merged'

  return (
    <div className='bg-card/50 rounded-lg border p-2.5 sm:p-3'>
      {/* 筛选行（primaryFilters 网格） */}
      <div className='grid gap-2 sm:grid-cols-[repeat(auto-fit,minmax(10rem,1fr))] sm:items-start'>
        <div className='relative'>
          <Search
            aria-hidden='true'
            className='text-muted-foreground absolute start-2 top-1/2 size-3.5 -translate-y-1/2'
          />
          <Input
            ref={searchRef}
            value={searchInput}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder='搜索任务名称、描述或标签'
            className='h-8 w-full sm:w-[200px] lg:w-[240px] ps-7'
            aria-label='搜索任务'
          />
        </div>
        <SingleFacet
          label='执行状态'
          value={filters.executionStatus}
          options={EXECUTION_STATUS_OPTIONS}
          onChange={(v) => update({ executionStatus: v })}
        />
        {isDaily && (
          <SingleFacet
            label='评估状态'
            value={filters.evaluationStatus}
            options={EVALUATION_STATUS_OPTIONS}
            onChange={(v) => update({ evaluationStatus: v })}
          />
        )}
        <MultiFacet
          label='标签'
          value={filters.tags ?? []}
          options={TASK_TAG_OPTIONS}
          onChange={(tags) => update({ tags })}
        />
        <SelectFilter
          label='时间范围'
          value={filters.timeRange ?? 'all'}
          options={TIME_RANGE_OPTIONS}
          onChange={(timeRange) => update({ timeRange })}
        />
        {isPublished && (
          <SingleFacet
            label='任务类型'
            value={filters.type}
            options={PUBLISHED_TYPE_OPTIONS}
            onChange={(v) => update({ type: v })}
          />
        )}
        {isPublished && (
          <SingleFacet
            label='发布状态'
            value={filters.ptStatus}
            options={PUBLISHED_STATUS_OPTIONS}
            onChange={(v) => update({ ptStatus: v })}
          />
        )}
        {isMerged && (
          <SingleFacet
            label='合并状态'
            value={filters.mergeStatus}
            options={MERGE_STATUS_OPTIONS}
            onChange={(v) => update({ mergeStatus: v })}
          />
        )}
        {hasPermission('task:read') && <GlobalAlgorithmChip />}
        {isDaily && hasPermission('task:read') && (
          <FavoriteTrashToggle
            value={{ favorite: filters.favorite ?? false, trash: filters.trash ?? false }}
            onChange={(v) => update({ favorite: v.favorite, trash: v.trash })}
          />
        )}
      </div>

      {/* stats 徽章行（日常页签） + 动作行 */}
      <div className='mt-2.5 flex flex-wrap items-center justify-between gap-2'>
        {isDaily ? <TasksStatsRow /> : <div />}
        <div className='flex flex-wrap items-center gap-1.5'>
          <Button
            variant='ghost'
            size='sm'
            aria-expanded={advancedOpen}
            className='text-primary h-8 gap-1 px-2.5'
            onClick={() => setAdvancedOpen((v) => !v)}
          >
            <SlidersHorizontal aria-hidden='true' className='size-3.5' />
            {advancedOpen ? '收起' : '展开'}
            <span className='text-primary bg-primary/10 inline-flex size-5 items-center justify-center rounded-full text-[11px] font-semibold tabular-nums'>
              2
            </span>
            <ChevronDown
              aria-hidden='true'
              className={cn('size-3.5 transition-transform', advancedOpen && 'rotate-180')}
            />
          </Button>
          {isFiltered && (
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
          <Button size='sm' className='h-8 gap-1.5 px-2.5' onClick={() => {
            onSearch()
            toast.success('筛选已应用')
          }}>
            <Search aria-hidden='true' className='size-3.5' />
            查询
          </Button>
        </div>
      </div>

      {/* 高级筛选展开区（自定义日期 + 算法参数关键字） */}
      {advancedOpen && (
        <div className='border-border/60 mt-2.5 grid gap-2 rounded-lg border p-2.5 sm:grid-cols-[repeat(auto-fit,minmax(10rem,1fr))]'>
          {filters.timeRange === 'custom' ? (
            <>
              <Input
                type='date'
                defaultValue='2026-10-01'
                aria-label='开始日期'
                className='h-8 w-full'
              />
              <span className='text-muted-foreground flex h-8 items-center'>至</span>
              <Input
                type='date'
                defaultValue='2026-10-15'
                aria-label='结束日期'
                className='h-8 w-full'
              />
            </>
          ) : (
            <div className='text-muted-foreground flex h-8 items-center gap-2 text-xs'>
              <CalendarDays aria-hidden='true' className='size-3.5' />
              选择「自定义」时间范围后，此处显示开始/结束日期
            </div>
          )}
          <Input
            placeholder='按算法参数关键字过滤（可选）'
            className='h-8 w-full'
            aria-label='算法参数过滤'
          />
        </div>
      )}
    </div>
  )
}

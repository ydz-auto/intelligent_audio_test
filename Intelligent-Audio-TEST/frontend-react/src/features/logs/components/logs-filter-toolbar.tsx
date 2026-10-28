/**
 * 日志筛选工具栏（interfaces 层；17_配置运维.md §4.2 LogsFilterToolbar）。
 * 搜索「搜索日志内容...」+ 分类/模块/标记/算法 Select + 级别 tag 多选 + 时间范围
 * （datetime-local 双框，对齐 Vue LogFilterPanel 语义）+ 高级过滤折叠
 * （设备ID/任务ID/评估ID/用户ID/线程ID/内容包含/内容不包含）+ 清除过滤器。
 * 算法筛选与全局切换器联动（§2.2：切换全局算法后同步为当前全局算法，可改选）。
 */
import { ChevronDown, ChevronUp, Eraser, Search } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import type { AlgorithmSwitchOption } from '@/domain/models/algorithm'
import {
  LOG_CATEGORY_OPTIONS,
  LOG_LEVEL_OPTIONS,
  LOG_MARK_FILTER_OPTIONS,
  LOG_MODULE_OPTIONS,
} from '@/features/logs/constants'

export type LogAdvancedFilters = {
  deviceId: string
  taskId: string
  evaluationId: string
  userId: string
  threadId: string
  contentInclude: string
  contentExclude: string
}

export type LogsFilterToolbarProps = {
  searchValue: string
  onSearchInput: (value: string) => void
  category: string
  onCategory: (value: string) => void
  module: string
  onModule: (value: string) => void
  markFilter: string
  onMarkFilter: (value: string) => void
  algorithmType: string
  onAlgorithmType: (value: string) => void
  algorithmOptions: AlgorithmSwitchOption[]
  startTime: string
  onStartTime: (value: string) => void
  endTime: string
  onEndTime: (value: string) => void
  selectedLevels: string[]
  onToggleLevel: (value: string) => void
  advanced: LogAdvancedFilters
  onAdvancedChange: (patch: Partial<LogAdvancedFilters>) => void
  onReset: () => void
  isFetching: boolean
  hasActiveFilters: boolean
}

function LevelChips({
  selected,
  onToggle,
}: {
  selected: string[]
  onToggle: (value: string) => void
}) {
  return (
    <div className='flex flex-wrap items-center gap-1'>
      {LOG_LEVEL_OPTIONS.map((level) => {
        const active = selected.includes(level.value)
        return (
          <button
            key={level.value}
            type='button'
            onClick={() => onToggle(level.value)}
            aria-pressed={active}
            className={cn(
              'inline-flex h-6 items-center gap-1 rounded-md border px-2 font-mono text-[11px] transition-colors',
              active
                ? 'border-primary/40 bg-primary/10 text-foreground'
                : 'border-border/60 text-muted-foreground hover:bg-muted/50'
            )}
          >
            {level.label}
            {active && <span aria-hidden='true' className='text-muted-foreground'>×</span>}
          </button>
        )
      })}
    </div>
  )
}

export function LogsFilterToolbar(props: LogsFilterToolbarProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false)

  // 算法 Select 的 items：『全部算法』+ 全局算法选项（关闭态由 Select.Value 按此映射回显 label）
  const algorithmItems = useMemo(
    () => [
      { value: 'all', label: '全部算法' },
      ...props.algorithmOptions.map((option) => ({ value: option.value, label: option.name })),
    ],
    [props.algorithmOptions]
  )

  const hasAdvanced = Object.values(props.advanced).some(Boolean)
  const advancedText = hasAdvanced
    ? `${advancedOpen ? '收起' : '展开'}高级过滤（${Object.values(props.advanced).filter(Boolean).length} 项）`
    : `${advancedOpen ? '收起' : '展开'}高级过滤`

  return (
    <div className='bg-card ring-foreground/10 flex flex-col gap-2 rounded-xl p-2.5 ring-1'>
      {/* 主行：搜索 + 分类 + 模块 + 标记 + 算法 */}
      <div className='flex flex-wrap items-center gap-2'>
        <div className='relative min-w-0 flex-1 basis-56'>
          <Search
            aria-hidden='true'
            className='text-muted-foreground absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2'
          />
          <Input
            aria-label='搜索日志内容'
            value={props.searchValue}
            onChange={(e) => props.onSearchInput(e.target.value)}
            placeholder='搜索日志内容...'
            className='h-8 pl-8'
          />
        </div>

        <Select
          value={props.category}
          onValueChange={(v) => props.onCategory(v ?? 'all')}
          items={LOG_CATEGORY_OPTIONS}
        >
          <SelectTrigger size='sm' className='w-32' aria-label='分类'>
            <SelectValue placeholder='所有分类' />
          </SelectTrigger>
          <SelectContent>
            {LOG_CATEGORY_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={props.module}
          onValueChange={(v) => props.onModule(v ?? 'all')}
          items={LOG_MODULE_OPTIONS}
        >
          <SelectTrigger size='sm' className='w-32' aria-label='模块'>
            <SelectValue placeholder='所有模块' />
          </SelectTrigger>
          <SelectContent>
            {LOG_MODULE_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={props.markFilter}
          onValueChange={(v) => props.onMarkFilter(v ?? 'all')}
          items={LOG_MARK_FILTER_OPTIONS}
        >
          <SelectTrigger size='sm' className='w-32' aria-label='标记筛选'>
            <SelectValue placeholder='所有标记' />
          </SelectTrigger>
          <SelectContent>
            {LOG_MARK_FILTER_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

      </div>

      {/* 第二行：时间范围 + 级别 tag + 操作 */}
      <div className='flex flex-wrap items-center gap-2'>
        <div className='flex items-center gap-1.5'>
          <Input
            aria-label='开始时间'
            type='datetime-local'
            value={props.startTime}
            onChange={(e) => props.onStartTime(e.target.value)}
            className='h-8 w-44 font-mono text-xs'
          />
          <span className='text-muted-foreground text-xs'>至</span>
          <Input
            aria-label='结束时间'
            type='datetime-local'
            value={props.endTime}
            onChange={(e) => props.onEndTime(e.target.value)}
            className='h-8 w-44 font-mono text-xs'
          />
        </div>

        <div className='flex items-center gap-1'>
          <span className='text-muted-foreground text-xs'>日志级别</span>
          <LevelChips selected={props.selectedLevels} onToggle={props.onToggleLevel} />
        </div>

        <div className='ml-auto flex items-center gap-1.5'>
          <Button
            variant='ghost'
            size='sm'
            className='h-7 gap-1 text-xs'
            onClick={() => setAdvancedOpen((prev) => !prev)}
            aria-expanded={advancedOpen}
          >
            {advancedOpen ? (
              <ChevronUp aria-hidden='true' className='size-3.5' />
            ) : (
              <ChevronDown aria-hidden='true' className='size-3.5' />
            )}
            {advancedText}
          </Button>
          <Button
            variant='outline'
            size='sm'
            className='h-7 gap-1 text-xs'
            disabled={!props.hasActiveFilters && !props.isFetching}
            onClick={props.onReset}
          >
            <Eraser aria-hidden='true' className='size-3.5' />
            清除过滤器
          </Button>
        </div>
      </div>

      {/* 高级过滤折叠区（§4.2：设备ID/任务ID/评估ID/用户ID/线程ID/内容包含/内容不包含） */}
      {advancedOpen && (
        <div className='bg-muted/30 grid gap-2 rounded-lg border p-2.5 sm:grid-cols-2 lg:grid-cols-3'>
          <AdvancedInput
            label='设备ID'
            value={props.advanced.deviceId}
            onChange={(v) => props.onAdvancedChange({ deviceId: v })}
          />
          <AdvancedInput
            label='任务ID'
            value={props.advanced.taskId}
            onChange={(v) => props.onAdvancedChange({ taskId: v })}
          />
          <AdvancedInput
            label='评估ID/轮次'
            value={props.advanced.evaluationId}
            onChange={(v) => props.onAdvancedChange({ evaluationId: v })}
          />
          <AdvancedInput
            label='用户ID'
            value={props.advanced.userId}
            onChange={(v) => props.onAdvancedChange({ userId: v })}
          />
          <AdvancedInput
            label='线程ID'
            value={props.advanced.threadId}
            onChange={(v) => props.onAdvancedChange({ threadId: v })}
          />
          <AdvancedInput
            label='日志内容包含'
            value={props.advanced.contentInclude}
            onChange={(v) => props.onAdvancedChange({ contentInclude: v })}
          />
          <AdvancedInput
            label='日志内容不包含'
            value={props.advanced.contentExclude}
            onChange={(v) => props.onAdvancedChange({ contentExclude: v })}
          />
        </div>
      )}
    </div>
  )
}

function AdvancedInput({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className='flex items-center gap-2 text-xs'>
      <span className='text-muted-foreground w-20 shrink-0'>{label}</span>
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className='h-7 flex-1 text-xs'
      />
    </label>
  )
}

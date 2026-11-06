/**
 * 挑选筛选栏（18_挑选合并交互重设计.md §3.4，INT-600）。
 * LogsFilterToolbar 形态：搜索 + 来源任务/设备/结果类型（多选 Popover）+ 执行状态/评估状态
 * （单选 Select）+ 时间范围（Select）+ 重置。会话级记忆（§6.4：不持久化）。
 */
import { SlidersHorizontal, X } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'

import type { PickFilters } from '@/application/tasks/cherry-pick/use-cherry-pick-candidates'
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
import {
  PICK_EVALUATION_STATUS_OPTIONS,
  PICK_EXECUTION_STATUS_OPTIONS,
  PICK_TIME_RANGE_OPTIONS,
} from '@/features/tasks/cherry-pick/constants'

interface FacetOption {
  value: string
  label: string
}

/** 结果类型「全部」哨兵值（服务端 result_type 为等值过滤，单值） */
const RESULT_TYPE_ALL = '__all__'

/** 多选 facet（Popover + Checkbox 列表 + 计数 Badge，Command 搜索留给接线） */
function MultiFacet({
  label,
  options,
  selected,
  onChange,
}: {
  label: string
  options: FacetOption[]
  selected: string[]
  onChange: (next: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const count = selected.length

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant='outline'
            size='sm'
            className='h-7 gap-1 text-[0.8rem]'
            aria-label={label}
          />
        }
      >
        {label}
        {count > 0 && (
          <Badge className='ml-0.5 rounded-md px-1 text-[10px] font-normal'>
            {count}
          </Badge>
        )}
      </PopoverTrigger>
      <PopoverContent align='start' className='min-w-52 p-1.5'>
        <div className='max-h-60 overflow-y-auto'>
          {options.length === 0 ? (
            <p className='text-muted-foreground px-2 py-2 text-xs'>无选项</p>
          ) : (
            options.map((opt) => (
              <label
                key={opt.value}
                className='hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm'
              >
                <Checkbox
                  checked={selected.includes(opt.value)}
                  onCheckedChange={(checked) => {
                    if (checked) onChange([...selected, opt.value])
                    else onChange(selected.filter((v) => v !== opt.value))
                  }}
                />
                <span className='min-w-0 flex-1 truncate'>{opt.label}</span>
              </label>
            ))
          )}
        </div>
        {count > 0 && (
          <div className='border-border/60 mt-1 flex items-center justify-between border-t pt-1'>
            <Button
              variant='ghost'
              size='xs'
              className='text-muted-foreground h-6'
              onClick={() => onChange([])}
            >
              <X aria-hidden='true' className='size-3' />
              清除
            </Button>
            <span className='text-muted-foreground pr-1 text-[11px] tabular-nums'>
              已选 {count}
            </span>
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}

export interface PickFilterBarProps {
  filters: PickFilters
  onChange: (filters: PickFilters) => void
  /** 筛选项全部来自真实数据源：任务=pickable-tasks，设备/API/结果类型=候选树 meta（§8.2 第 2 条） */
  options: {
    tasks: { id: number; name: string }[]
    devices: { id: number; name: string }[]
    apis: { id: number; name: string }[]
    resultTypes: { value: string; label: string }[]
  }
  onReset: () => void
  /** §3.8.2 阶段 2：任务维度由阶段 1 锁定，隐藏「来源任务」facet */
  hideTaskFacet?: boolean
}

/** 挑选筛选栏（会话级记忆：state 由父向导持有，切页签不持久） */
export function PickFilterBar({
  filters,
  onChange,
  options,
  onReset,
  hideTaskFacet = false,
}: PickFilterBarProps) {
  const [searchDraft, setSearchDraft] = useState(filters.search ?? '')
  const searchTimer = useRef<number | null>(null)

  const taskOptions = useMemo<FacetOption[]>(
    () => options.tasks.map((t) => ({ value: String(t.id), label: t.name })),
    [options.tasks]
  )
  const deviceOptions = useMemo<FacetOption[]>(
    () => options.devices.map((d) => ({ value: String(d.id), label: d.name })),
    [options.devices]
  )
  const apiOptions = useMemo<FacetOption[]>(
    () => options.apis.map((a) => ({ value: String(a.id), label: a.name })),
    [options.apis]
  )
  const resultTypeOptions = useMemo<FacetOption[]>(
    () => options.resultTypes.map((rt) => ({ value: rt.value, label: rt.label })),
    [options.resultTypes]
  )
  const resultTypeValue = filters.resultType[0] ?? RESULT_TYPE_ALL

  const isFiltered =
    searchDraft.trim() !== '' ||
    (hideTaskFacet ? false : filters.taskIds.length > 0) ||
    filters.deviceIds.length > 0 ||
    filters.apiIds.length > 0 ||
    filters.resultType.length > 0 ||
    filters.executionStatus.length > 0 ||
    filters.evaluationStatus.length > 0 ||
    filters.timeRange !== 'all'

  return (
    <div className='flex flex-wrap items-center gap-2'>
      <SlidersHorizontal aria-hidden='true' className='text-muted-foreground size-4' />
      <Input
        value={searchDraft}
        onChange={(e) => {
          const value = e.target.value
          setSearchDraft(value)
          // debounce 500ms（§3.4 搜索命中用例名/用例 ID）
          if (searchTimer.current) window.clearTimeout(searchTimer.current)
          searchTimer.current = window.setTimeout(
            () => onChange({ ...filters, search: value }),
            500
          )
        }}
        placeholder='搜索用例名称或 ID'
        className='h-7 w-44 text-[0.8rem]'
        aria-label='搜索用例名称或 ID'
      />
      {!hideTaskFacet && (
        <MultiFacet
          label='来源任务'
          options={taskOptions}
          selected={filters.taskIds.map(String)}
          onChange={(values) =>
            onChange({
              ...filters,
              taskIds: values.map((v) => Number(v)),
            })
          }
        />
      )}
      <MultiFacet
        label='设备'
        options={deviceOptions}
        selected={filters.deviceIds.map(String)}
        onChange={(values) =>
          onChange({ ...filters, deviceIds: values.map((v) => Number(v)) })
        }
      />
      {/* API 维度选项来自候选树 meta.apis（可挑范围无 API 结果时为空 → 无选项） */}
      <MultiFacet
        label='API'
        options={apiOptions}
        selected={filters.apiIds.map(String)}
        onChange={(values) =>
          onChange({ ...filters, apiIds: values.map((v) => Number(v)) })
        }
      />
      {/* 结果类型服务端为等值过滤（单值），选项来自当前树内的 result_type 集合 */}
      <Select
        value={resultTypeValue}
        onValueChange={(value) =>
          onChange({
            ...filters,
            resultType: !value || value === RESULT_TYPE_ALL ? [] : [value],
          })
        }
      >
        <SelectTrigger size='sm' aria-label='结果类型'>
          <SelectValue placeholder='结果类型'>
            {resultTypeOptions.find((o) => o.value === filters.resultType[0])?.label ??
              '结果类型'}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={RESULT_TYPE_ALL}>全部结果类型</SelectItem>
          {resultTypeOptions.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select
        value={filters.executionStatus.length > 0 ? filters.executionStatus[0] : undefined}
        onValueChange={(value) =>
          onChange({
            ...filters,
            executionStatus: value ? [value] : [],
          })
        }
      >
        <SelectTrigger size='sm' aria-label='执行状态'>
          <SelectValue placeholder='执行状态'>
            {PICK_EXECUTION_STATUS_OPTIONS.find(
              (o) => o.value === (filters.executionStatus[0] ?? '')
            )?.label ?? '执行状态'}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {PICK_EXECUTION_STATUS_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select
        value={filters.evaluationStatus.length > 0 ? filters.evaluationStatus[0] : undefined}
        onValueChange={(value) =>
          onChange({
            ...filters,
            evaluationStatus: value ? [value] : [],
          })
        }
      >
        <SelectTrigger size='sm' aria-label='评估状态'>
          <SelectValue placeholder='评估状态'>
            {PICK_EVALUATION_STATUS_OPTIONS.find(
              (o) => o.value === (filters.evaluationStatus[0] ?? '')
            )?.label ?? '评估状态'}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {PICK_EVALUATION_STATUS_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select
        value={filters.timeRange}
        onValueChange={(value) => onChange({ ...filters, timeRange: value ?? 'all' })}
      >
        <SelectTrigger size='sm' aria-label='时间范围'>
          <SelectValue placeholder='时间范围'>
            {PICK_TIME_RANGE_OPTIONS.find((o) => o.value === filters.timeRange)?.label ??
              '时间范围'}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {PICK_TIME_RANGE_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button
        variant='ghost'
        size='sm'
        className='text-muted-foreground h-7 text-[0.8rem]'
        disabled={!isFiltered}
        onClick={() => {
          setSearchDraft('')
          onReset()
        }}
      >
        <X aria-hidden='true' className='size-3.5' />
        重置
      </Button>
    </div>
  )
}

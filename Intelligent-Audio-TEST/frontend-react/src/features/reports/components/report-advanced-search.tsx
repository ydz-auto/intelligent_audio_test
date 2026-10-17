/**
 * 报告中心高级搜索（15_报告域.md §2 + 报告管理功能设计文档.md:173-193 实测；INT-381 返修）。
 * SearchBar 展开「高级搜索」折叠区：任务类型 × 设备类型 × 创建者 × 时间范围多条件表单；
 * 工具栏排序下拉兜底。状态由 URL search（taskType/deviceType/creator）承载，页面以 navigate 回写。
 */
import { ChevronDown } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { ReportTimeRange } from '@/domain/models/report'
import { cn } from '@/lib/utils'

import { TIME_RANGE_OPTIONS } from '@/features/reports/constants'

const TASK_TYPE_OPTIONS = [
  { value: 'e2e', label: 'e2e 端到端' },
  { value: 'api', label: 'api 接口' },
  { value: 'mixed', label: 'mixed 混合' },
  { value: 'benchmark', label: 'Benchmark' },
]

const DEVICE_TYPE_OPTIONS = [
  { value: 'smart_speaker', label: '智能音箱' },
  { value: 'car_voice', label: '车载助手' },
  { value: 'headphone', label: '耳机' },
  { value: 'mixed', label: '混合' },
]

const CREATOR_OPTIONS = [
  { value: 'demo_admin', label: 'demo_admin' },
  { value: 'algo_engineer', label: 'algo_engineer' },
]

interface ReportAdvancedSearchProps {
  taskType?: string
  deviceType?: string
  creator?: string
  /** 高级搜索时间范围（§2 :117：任务类型 × 设备类型 × 创建者 × 时间范围多条件表单） */
  timeRange?: ReportTimeRange | 'all'
  onTimeRangeChange: (value: ReportTimeRange | 'all') => void
  onChange: (patch: { taskType?: string; deviceType?: string; creator?: string }) => void
  onReset: () => void
}

export function ReportAdvancedSearch({
  taskType,
  deviceType,
  creator,
  timeRange,
  onTimeRangeChange,
  onChange,
  onReset,
}: ReportAdvancedSearchProps) {
  const [open, setOpen] = useState(false)
  const hasActive = Boolean(taskType || deviceType || creator || (timeRange && timeRange !== 'all'))

  return (
    <div className='mt-2'>
      <button
        type='button'
        className={cn(
          'text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs font-medium transition-colors',
          hasActive && 'text-primary'
        )}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        高级搜索
        <ChevronDown
          aria-hidden='true'
          className={cn('size-3.5 transition-transform', open && 'rotate-180')}
        />
        {hasActive && (
          <span className='bg-primary text-primary-foreground ms-1 rounded-full px-1.5 text-[10px] tabular-nums'>
            {[taskType, deviceType, creator, timeRange && timeRange !== 'all' ? timeRange : undefined].filter(Boolean).length}
          </span>
        )}
      </button>

      {open && (
        <div className='bg-muted/40 mt-2 flex flex-wrap items-end gap-3 rounded-xl border p-3'>
          <div className='flex flex-col gap-1.5'>
            <label htmlFor='adv-task-type' className='text-muted-foreground text-xs font-medium'>
              任务类型
            </label>
            <Select
              value={taskType ?? 'all'}
              onValueChange={(v) => onChange({ taskType: v === 'all' ? undefined : v ?? undefined })}
            >
              <SelectTrigger id='adv-task-type' className='h-9 w-40'>
                <SelectValue placeholder='全部' />
              </SelectTrigger>
              <SelectContent align='start'>
                <SelectItem value='all'>全部</SelectItem>
                {TASK_TYPE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className='flex flex-col gap-1.5'>
            <label htmlFor='adv-device-type' className='text-muted-foreground text-xs font-medium'>
              设备类型
            </label>
            <Select
              value={deviceType ?? 'all'}
              onValueChange={(v) => onChange({ deviceType: v === 'all' ? undefined : v ?? undefined })}
            >
              <SelectTrigger id='adv-device-type' className='h-9 w-40'>
                <SelectValue placeholder='全部' />
              </SelectTrigger>
              <SelectContent align='start'>
                <SelectItem value='all'>全部</SelectItem>
                {DEVICE_TYPE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className='flex flex-col gap-1.5'>
            <label htmlFor='adv-creator' className='text-muted-foreground text-xs font-medium'>
              创建者
            </label>
            <Select
              value={creator ?? 'all'}
              onValueChange={(v) => onChange({ creator: v === 'all' ? undefined : v ?? undefined })}
            >
              <SelectTrigger id='adv-creator' className='h-9 w-40'>
                <SelectValue placeholder='全部' />
              </SelectTrigger>
              <SelectContent align='start'>
                <SelectItem value='all'>全部</SelectItem>
                {CREATOR_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className='flex flex-col gap-1.5'>
            <label htmlFor='adv-time-range' className='text-muted-foreground text-xs font-medium'>
              时间范围
            </label>
            <Select
              value={timeRange ?? 'all'}
              onValueChange={(v) => onTimeRangeChange(v as ReportTimeRange | 'all')}
            >
              <SelectTrigger id='adv-time-range' className='h-9 w-36'>
                <SelectValue placeholder='全部时间' />
              </SelectTrigger>
              <SelectContent align='start'>
                {TIME_RANGE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Button variant='outline' size='sm' className='h-9' onClick={onReset}>
            重置高级搜索
          </Button>
        </div>
      )}
    </div>
  )
}

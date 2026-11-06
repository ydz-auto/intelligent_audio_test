/**
 * 统计维度选择卡（15_报告域.md §2.2：选择统计维度 → 设置统计时间范围 → 执行统计分析）。
 * 维度 Select（时间/设备类型/评估维度）+ 时间范围 Input（CompactDateTimeRangePicker 对位）
 * +「执行统计分析」主按钮；流程 §4.4 实测。数据经 application/use-report-statistics 取数。
 * INT-1297：移除「任务类型」维度选项。
 */
import { BarChart3 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  STATISTIC_DIMENSIONS,
  type StatisticDimension,
} from '@/features/report-statistics/constants'
import type { StatisticsTimeRange } from '@/application/report-statistics/use-report-statistics'

interface StatisticsDimensionSelectProps {
  dimension: StatisticDimension
  onDimensionChange: (value: StatisticDimension) => void
  range: StatisticsTimeRange
  onRangeChange: (range: StatisticsTimeRange) => void
  onRun: () => void
}

export function StatisticsDimensionSelect({
  dimension,
  onDimensionChange,
  range,
  onRangeChange,
  onRun,
}: StatisticsDimensionSelectProps) {
  return (
    <div className='bg-card rounded-2xl border shadow-xs p-4 sm:p-5'>
      <div className='flex flex-wrap items-end gap-3'>
        <div className='flex min-w-48 flex-col gap-1.5'>
          <label htmlFor='statistic-dimension' className='text-muted-foreground text-xs font-medium'>
            统计维度
          </label>
          <Select value={dimension} onValueChange={(v) => onDimensionChange(v as StatisticDimension)}>
            <SelectTrigger id='statistic-dimension' className='h-9 w-48'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent align='start'>
              {STATISTIC_DIMENSIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className='flex flex-col gap-1.5'>
          <span className='text-muted-foreground text-xs font-medium'>统计时间范围</span>
          <div className='flex items-center gap-2'>
            <Input
              type='datetime-local'
              aria-label='开始时间'
              value={range.start ?? ''}
              onChange={(e) => onRangeChange({ ...range, start: e.target.value || undefined })}
              className='h-9 w-[190px] text-sm tabular-nums'
            />
            <span className='text-muted-foreground text-xs'>至</span>
            <Input
              type='datetime-local'
              aria-label='结束时间'
              value={range.end ?? ''}
              onChange={(e) => onRangeChange({ ...range, end: e.target.value || undefined })}
              className='h-9 w-[190px] text-sm tabular-nums'
            />
          </div>
        </div>

        <Button size='sm' className='h-9 font-medium' onClick={onRun}>
          <BarChart3 data-icon='inline-start' />
          执行统计分析
        </Button>
      </div>
      <p className='text-muted-foreground mt-3 text-xs leading-5'>
        统计流程：选择统计维度 → 设置统计时间范围 → 执行统计分析 → 计算统计指标 → 生成统计图表 → 显示统计结果 → 导出。
      </p>
    </div>
  )
}

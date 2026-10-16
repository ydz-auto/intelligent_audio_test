/**
 * 基线差文案（对位 newAPI GrowthText，按指标 direction 定正负色，14_benchmark排行.md §5.4）。
 * higher_is_better：delta > 0（超基线）→ success 绿 ↑；< 0 → destructive 红 ↓。
 * lower_is_better：delta < 0（低于基线=更优）→ success 绿 ↓；> 0 → destructive 红 ↑。
 * 显示 ±{|delta| 保留 2 位}{unit}；0 或空显示「—」（neutral）。
 */
import { ArrowDown, ArrowUp } from 'lucide-react'

import type { BenchmarkDirection } from '@/domain/models/benchmark'
import { formatGap } from '@/features/rankings/lib/format'
import { cn } from '@/lib/utils'

export function DeltaText(props: {
  value: number | null
  unit: string
  direction: BenchmarkDirection
  className?: string
}) {
  const gap = formatGap(props.value, props.unit)

  if (gap === null) {
    return (
      <span className={cn('text-muted-foreground tabular-nums', props.className)}>
        —
      </span>
    )
  }

  const positiveIsBetter = props.direction === 'higher_is_better'
  const better = positiveIsBetter ? props.value! > 0 : props.value! < 0
  const up = props.value! > 0

  return (
    <span
      className={cn(
        'tabular-nums inline-flex items-center gap-0.5',
        better
          ? 'text-success dark:text-emerald-400'
          : 'text-destructive dark:text-rose-400',
        props.className
      )}
      title={better ? '优于基线' : '劣于基线'}
    >
      {up ? (
        <ArrowUp aria-hidden='true' className='size-3' />
      ) : (
        <ArrowDown aria-hidden='true' className='size-3' />
      )}
      {gap}
    </span>
  )
}

/**
 * 指标值横向对比条形图（14_benchmark排行.md §4.4 图表区）：
 * VChart 横向条形，rank 升序自上而下，实测轨 --chart-1 / 外部轨 --chart-2。
 * useChartTheme 就绪门控 + themeKey/presetKey 整图重建；深浅色轴色照 §1.2 实测值。
 */
import { VChart } from '@visactor/react-vchart'
import type { ISpec } from '@visactor/vchart'

import type { RankingGroup } from '@/domain/models/benchmark'
import {
  useChartTheme,
  useThemePresetKey,
  VCHART_OPTION,
} from '@/features/dashboard/lib/vchart'
import {
  buildMetricBarSpec,
  toMetricBarData,
} from '@/features/rankings/lib/charts'
import { cn } from '@/lib/utils'

const LIGHT_AXIS_LABEL = 'rgba(15,23,42,0.58)'
const LIGHT_GRID = 'rgba(15,23,42,0.12)'
const DARK_AXIS_LABEL = 'rgba(255,255,255,0.68)'
const DARK_GRID = 'rgba(255,255,255,0.12)'

/** 读取 CSS 语义 token（--chart-1/2），随多主题预设联动（§5.5） */
function resolveChartColor(cssVariable: '--chart-1' | '--chart-2'): string {
  if (typeof document === 'undefined') return cssVariable
  const resolved = getComputedStyle(document.documentElement)
    .getPropertyValue(cssVariable)
    .trim()
  return resolved || cssVariable
}

export function MetricBarChart(props: {
  group: RankingGroup
  className?: string
}) {
  const { themeReady, themeKey, resolvedTheme } = useChartTheme()
  const presetKey = useThemePresetKey()
  const values = toMetricBarData(props.group.rows)
  const dark = resolvedTheme === 'dark'

  const ready = themeReady && values.length > 0

  return (
    <div className={cn('h-60 sm:h-72', props.className)}>
      {!ready ? (
        <div className='text-muted-foreground/80 flex h-full w-full items-center justify-center rounded-lg border border-dashed text-sm'>
          暂无图表数据
        </div>
      ) : (
        <VChart
          key={[props.group.metricCode, themeKey, presetKey].join('-')}
          spec={
            {
              ...buildMetricBarSpec(values, {
                chart1: resolveChartColor('--chart-1'),
                chart2: resolveChartColor('--chart-2'),
                axisLabelColor: dark ? DARK_AXIS_LABEL : LIGHT_AXIS_LABEL,
                gridColor: dark ? DARK_GRID : LIGHT_GRID,
              }),
              theme: themeKey,
              background: 'transparent',
            } as ISpec
          }
          options={VCHART_OPTION}
        />
      )}
    </div>
  )
}

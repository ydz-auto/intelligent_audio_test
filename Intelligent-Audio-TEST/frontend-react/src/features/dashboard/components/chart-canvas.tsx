/**
 * 工作台图表画布（heavy 模块）：唯一静态引入 @visactor/react-vchart 与 spec 构造器的入口。
 * 只被 lazy-chart-canvas 动态 import——视口外不下载 VChart 分块（约 2MB）。
 */
import { VChart } from '@visactor/react-vchart'
import type { ISpec } from '@visactor/vchart'
import { useMemo } from 'react'

import type { TrendPoint } from '@/domain/models/stats'
import { getTaskStatusLabel } from '@/features/dashboard/constants'
import {
  buildDistributionPieSpec,
  buildTrendSpec,
} from '@/features/dashboard/lib/charts'
import {
  useChartTheme,
  useThemePresetKey,
  VCHART_OPTION,
} from '@/features/dashboard/lib/vchart'

export type DashboardChartProps =
  | {
      kind: 'trend'
      trend: TrendPoint[]
      variant: 'bar' | 'area'
      chartRadius?: number
    }
  | {
      kind: 'status'
      statusCounts: Record<string, number>
      chartRadius?: number
    }

export function DashboardChart(props: DashboardChartProps) {
  const { themeReady, themeKey } = useChartTheme()
  const presetKey = useThemePresetKey()

  const trend = props.kind === 'trend' ? props.trend : null
  const variant = props.kind === 'trend' ? props.variant : null
  const statusCounts = props.kind === 'status' ? props.statusCounts : null
  const chartRadius = props.chartRadius

  const spec = useMemo(() => {
    if (trend !== null && variant !== null) {
      return buildTrendSpec(trend, { variant, chartRadius })
    }
    const values = Object.entries(statusCounts ?? {}).map(([status, value]) => ({
      type: getTaskStatusLabel(status),
      value,
    }))
    return buildDistributionPieSpec(values, { chartRadius })
  }, [trend, variant, statusCounts, chartRadius])

  if (!themeReady) return null

  return (
    <VChart
      // 主题/预设/数据变化整图重建（key 含 themeKey/presetKey —— newAPI 同款机制）
      key={[spec.type, themeKey, presetKey].join('-')}
      spec={
        {
          ...spec,
          theme: themeKey,
          background: 'transparent',
        } as ISpec
      }
      options={VCHART_OPTION}
    />
  )
}

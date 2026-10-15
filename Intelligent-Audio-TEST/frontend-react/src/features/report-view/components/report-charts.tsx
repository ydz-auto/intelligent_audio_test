/**
 * 评估指标图表区（规范 §4.5，VChart 柱状/折线/雷达；图表组件对齐 newAPI）。
 * 主题适配：useChartTheme（ThemeManager 门控 + themeKey 整图重建）+ useThemePresetKey
 * （预设变化重建，series 色走 --chart-1..5 语义 token）+ background:'transparent'。
 * 空数据 → 占位卡「暂无图表数据」。
 */
import { VChart } from '@visactor/react-vchart'
import type { ISpec } from '@visactor/vchart'
import { BarChart3, LineChart, Radar as RadarIcon } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'

import { IconBadge } from '@/components/ui/icon-badge'
import {
  useChartTheme,
  useThemePresetKey,
  useThemeRadiusPx,
  VCHART_OPTION,
} from '@/features/dashboard/lib/vchart'
import type { ReportDetailData } from '@/domain/models/report'

import {
  buildMetricBarSpec,
  buildPassRateTrendSpec,
  buildRadarSpec,
  getChartThemeTokens,
  isEmptyChartData,
  resolveChartColors,
} from '@/application/report-view/use-report-charts'

function ChartCard({
  title,
  icon,
  tone,
  children,
}: {
  title: string
  icon: ReactNode
  tone: 'chart-1' | 'chart-4'
  children: ReactNode
}) {
  return (
    <div className='overflow-hidden rounded-lg border'>
      <div className='flex w-full items-center gap-2 border-b px-3 py-2 sm:px-4'>
        <IconBadge tone={tone} size='sm'>
          {icon}
        </IconBadge>
        <div className='text-sm font-semibold'>{title}</div>
      </div>
      <div className='p-2 sm:p-3'>{children}</div>
    </div>
  )
}

function ChartCanvas({ spec }: { spec: Record<string, unknown> | null }) {
  const { themeReady, themeKey } = useChartTheme()
  const presetKey = useThemePresetKey()

  if (!spec) {
    return (
      <div className='text-muted-foreground flex h-48 items-center justify-center rounded-lg border text-xs'>
        暂无图表数据
      </div>
    )
  }
  if (!themeReady) return null

  return (
    <VChart
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

export function ReportCharts({ report }: { report: ReportDetailData }) {
  const { resolvedTheme } = useChartTheme()
  const presetKey = useThemePresetKey()
  const chartRadius = useThemeRadiusPx('--radius-md', `${presetKey}:${report.id}`)

  const metricData = report.summary.metric_data
  const resources = report.summary.resource_headers.map((r) => r.label)
  const colors = resolveChartColors(Math.max(resources.length, 3))

  // 资源 key → 标签（柱状/折线/雷达统一按 label 显示）
  const labelOf = (key: string) =>
    report.summary.resource_headers.find((r) => r.key === key)?.label ?? key
  const labeledMetricData = useMemo(
    () => metricData.map((group) => ({ ...group, resource: labelOf(group.resource) })),
    [metricData, labelOf]
  )

  const barSpec = useMemo(
    () =>
      buildMetricBarSpec(labeledMetricData, resources, {
        chartRadius,
        colors,
        ...getChartThemeTokens(resolvedTheme),
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [labeledMetricData, resources, chartRadius, presetKey, resolvedTheme, report.id]
  )

  const lineSpec = useMemo(
    () =>
      buildPassRateTrendSpec(labeledMetricData, {
        colors,
        ...getChartThemeTokens(resolvedTheme),
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [labeledMetricData, presetKey, resolvedTheme, report.id]
  )

  const radarSpec = useMemo(
    () =>
      buildRadarSpec(labeledMetricData, {
        colors,
        ...getChartThemeTokens(resolvedTheme),
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [labeledMetricData, presetKey, resolvedTheme, report.id]
  )

  const isEmpty = isEmptyChartData(metricData)

  if (isEmpty) {
    return (
      <div className='text-muted-foreground flex h-48 items-center justify-center rounded-lg border text-xs'>
        暂无图表数据
      </div>
    )
  }

  return (
    <div className='grid gap-4 xl:grid-cols-2'>
      <ChartCard title='指标对比' icon={<BarChart3 className='size-4' />} tone='chart-1'>
        <div className='h-64 sm:h-72'>
          <ChartCanvas spec={barSpec} />
        </div>
      </ChartCard>
      <ChartCard title='通过率趋势' icon={<LineChart className='size-4' />} tone='chart-4'>
        <div className='h-64 sm:h-72'>
          <ChartCanvas spec={lineSpec} />
        </div>
      </ChartCard>
      <ChartCard title='多维性能对比' icon={<RadarIcon className='size-4' />} tone='chart-1'>
        <div className='h-64 sm:h-72'>
          <ChartCanvas spec={radarSpec} />
        </div>
      </ChartCard>
    </div>
  )
}

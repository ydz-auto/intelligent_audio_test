/**
 * 统计图表（15_报告域.md §2.2/§3.7：散点图（两个变量关系）/ 热力图（密度分布））。
 * 复用共享 ReportChart（chart.js v4）：scatter 原生点图；heatmap 走 chartjs-chart-matrix
 * 色阶 alpha 分级。图表导出 PNG/SVG/PDF 由 ChartActions 承载（§3.7 图一）。
 */
import { useState } from 'react'

import { ReportChart } from '@/components/common/report-chart'
import type { ChartSeriesData } from '@/application/report-view/use-report-charts'
import { STATISTIC_CHART_TYPES } from '@/features/report-statistics/constants'
import { cn } from '@/lib/utils'

interface StatisticsChartsProps {
  scatter: ChartSeriesData
  heatmap: ChartSeriesData
  loading: boolean
}

export function StatisticsCharts({ scatter, heatmap, loading }: StatisticsChartsProps) {
  const [active, setActive] = useState<'scatter' | 'heatmap'>('scatter')

  return (
    <div className='space-y-3'>
      <div role='group' aria-label='统计图表类型' className='bg-muted/60 inline-flex items-center rounded-lg border p-0.5'>
        {STATISTIC_CHART_TYPES.map((option) => (
          <button
            key={option.value}
            type='button'
            className={cn(
              'rounded-md px-3 py-1 text-sm transition-colors',
              active === option.value ? 'bg-background shadow-sm' : 'text-muted-foreground'
            )}
            onClick={() => setActive(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {active === 'scatter' ? (
        <ReportChart
          title='通过率 × 平均响应时间'
          subtitle='各被测设备/API 的两变量关系分布'
          type='scatter'
          series={scatter}
          loading={loading}
          enableZoom
        />
      ) : (
        <ReportChart
          title='设备 × 评估维度 值矩阵'
          subtitle='密度分布：颜色越深值越高'
          type='heatmap'
          series={heatmap}
          loading={loading}
          enableZoom={false}
        />
      )}
    </div>
  )
}

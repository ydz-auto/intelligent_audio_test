/**
 * 分组/标签对比矩阵展示（15_报告域.md §3.6：每个评估维度一个 .metric-container）。
 * 显示类型切换：表格 / 柱状图 / 折线图 / 雷达图 / 正态分布图（默认表格）。
 * 单元格 formatMetricForDisplay + 单位；表头/单元格可编辑（commitEditCategory 重命名分组键——
 * 演示态本地改，编辑持久化见 use-report-summary-edit）。
 */
import { ChevronDown } from 'lucide-react'
import { useMemo, useState } from 'react'

import { cn } from '@/lib/utils'
import type { MetricMatrix, ReportMetricConfig } from '@/domain/models/report'
import { useReportCharts, type DisplayType } from '@/application/report-view/use-report-charts'
import { formatMetricForDisplay, getMetricUnit } from '@/application/report-view/use-report-summary'
import { readMatrixCell } from '@/application/report-view/case-matrix'
import { DISPLAY_TYPE_OPTIONS } from '@/application/report-view/use-case-category-comparison'

import { ReportChart } from '@/components/common/report-chart'

interface MetricMatrixTableProps {
  metric: ReportMetricConfig
  matrix: MetricMatrix
  groups: string[]
  resources: string[]
  displayType: DisplayType
  onDisplayTypeChange: (type: DisplayType) => void
  /** 导出模式（P2-12：强制展开 + 表格视图，canvas 图表不克隆进静态 HTML） */
  isExporting?: boolean
  /** 表头/单元格重命名（分组名/资源 label 编辑） */
  onRename?: (group: string, resource: string | undefined, next: string) => void
}

export function MetricMatrixTable({
  metric,
  matrix,
  groups,
  resources,
  displayType,
  onDisplayTypeChange,
  isExporting,
  onRename,
}: MetricMatrixTableProps) {
  const [collapsed, setCollapsed] = useState(false)
  const { series, distribution } = useReportCharts(matrix, groups, resources, metric.name, displayType)
  const forceOpen = Boolean(isExporting)
  const isDistribution = displayType === 'distribution' && !forceOpen

  const tableCells = useMemo(
    () =>
      groups.map((group) => ({
        group,
        cells: resources.map((resource) => readMatrixCell(matrix, group, resource, metric.name)),
      })),
    [matrix, groups, resources, metric.name]
  )

  const unit = metric.unit ?? getMetricUnit([], metric.name)

  return (
    <div className='rounded-xl border'>
      <div className='flex flex-wrap items-center justify-between gap-2 px-3 pt-3'>
        <button
          type='button'
          className='flex items-center gap-1 text-sm font-medium'
          onClick={() => !forceOpen && setCollapsed((v) => !v)}
        >
          {metric.name} 对比（单位：{unit || '—'}）
          {!forceOpen && (
            <ChevronDown
              aria-hidden='true'
              className={cn('text-muted-foreground size-4 transition-transform', collapsed && 'rotate-180')}
            />
          )}
        </button>
        <div className='flex flex-wrap gap-1'>
          {DISPLAY_TYPE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type='button'
              className={cn(
                'rounded-md px-2 py-1 text-xs transition-colors',
                displayType === option.value
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted'
              )}
              onClick={() => onDisplayTypeChange(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {(!collapsed || forceOpen) && (
        <div className='p-3'>
          {(displayType === 'table' || forceOpen) ? (
            <div className='overflow-x-auto rounded-lg border'>
              <table className='w-full min-w-[420px] text-sm'>
                <thead>
                  <tr className='text-muted-foreground border-b bg-muted/30'>
                    <th className='px-3 py-2 text-left font-medium'>
                      {metric.dimension_type === 'sub' ? '子维度' : '分组'}
                    </th>
                    {resources.map((resource) => (
                      <th key={resource} className='px-3 py-2 text-left font-medium'>
                        {resource}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tableCells.map(({ group, cells }) => (
                    <tr key={group} className='hover:bg-muted/30 border-b last:border-0'>
                      <td className='px-3 py-2 text-sm font-medium'>
                        {onRename ? (
                          <button
                            type='button'
                            className='hover:text-foreground text-muted-foreground text-left transition-colors'
                            onClick={() => onRename(group, undefined, `${group} (编辑)`) }
                            title='点击重命名分组'
                          >
                            {group}
                          </button>
                        ) : (
                          group
                        )}
                      </td>
                      {cells.map((cell, i) => (
                        <td key={i} className='px-3 py-2 font-mono text-xs tabular-nums'>
                          {formatMetricForDisplay(cell.average)}
                          {unit && <span className='text-muted-foreground ms-0.5'>{unit}</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {tableCells.length === 0 && (
                <p className='text-muted-foreground p-6 text-center text-sm'>暂无数据</p>
              )}
            </div>
          ) : (
            <ReportChart
              title={isDistribution ? '正态分布分析' : `${metric.name} 对比`}
              subtitle={isDistribution ? `不同区间的${metric.name}，每资源独立系列` : `单位：${unit || '—'} · 每资源独立系列`}
              type={displayType === 'distribution' ? 'distribution' : (displayType === 'bar' ? 'bar' : displayType === 'line' ? 'line' : 'radar')}
              series={series}
              distribution={distribution}
              xAxisTitle={isDistribution ? `不同区间的${metric.name}` : undefined}
              height={280}
            />
          )}
        </div>
      )}
    </div>
  )
}

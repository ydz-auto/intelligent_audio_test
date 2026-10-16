/**
 * 总览卡（15_报告域.md §3.3.1，OverviewCardComponent 对位）。
 * 统计行 StatCard ×3（用例总数/评估维度/资源数）+ 维度×资源矩阵表（主/子维度层级分组）。
 */
import { Layers, ListChecks, MonitorSpeaker } from 'lucide-react'

import { StatCard } from '@/features/dashboard/components/ui/stat-card'
import type { ReportDetailData, ReportMetricConfig } from '@/domain/models/report'

import {
  formatMetricForDisplay,
  getAverageValue,
  getMetricUnit,
  getNormalizedMetricData,
  getValidResources,
  groupMetricsByDimension,
  buildResourceHeaderMap,
} from '@/application/report-view/use-report-summary'

interface ReportOverviewCardProps {
  report: ReportDetailData
}

/** 维度行（主维度为组头，子维度缩进归组） */
function buildDimensionRows(allMetrics: ReportMetricConfig[]) {
  const { mainMetrics, subMetrics } = groupMetricsByDimension(allMetrics)
  const rows: { key: string; name: string; group: string; isGroupHeader: boolean; isSubDim: boolean; metricName: string }[] = []

  for (const main of mainMetrics) {
    const children = subMetrics.filter(
      (s) => s.parent_dimension_name === main.name || s.parent_dimension_id === main.id
    )
    rows.push({ key: `m-${main.id ?? main.name}`, name: main.name, group: main.name, isGroupHeader: false, isSubDim: false, metricName: main.name })
    // 组内有子维度且主维度名≠组名时插分组标题行（isGroupHeader 加粗）
    if (children.length > 0) {
      rows.push({ key: `g-${main.id ?? main.name}`, name: main.name, group: main.name, isGroupHeader: true, isSubDim: false, metricName: '' })
    }
    for (const child of children) {
      rows.push({ key: `s-${child.id ?? child.name}`, name: child.name, group: main.name, isGroupHeader: false, isSubDim: true, metricName: child.name })
    }
  }
  // 无父分组的子维度兜底（按中文名排序）
  const orphans = subMetrics.filter(
    (s) => !mainMetrics.some((m) => m.name === s.parent_dimension_name)
  )
  for (const orphan of orphans.sort((a, b) => a.name.localeCompare(b.name))) {
    rows.push({ key: `s-${orphan.id ?? orphan.name}`, name: orphan.name, group: '', isGroupHeader: false, isSubDim: true, metricName: orphan.name })
  }
  return rows
}

export function ReportOverviewCard({ report }: ReportOverviewCardProps) {
  const summary = report.summary
  const resources = getValidResources(summary)
  const metricData = getNormalizedMetricData(summary)
  const headerMap = buildResourceHeaderMap(summary)
  const rows = buildDimensionRows(summary.all_metrics)

  const resourceLabel = (key: string) => headerMap[key]?.label ?? key

  return (
    <div className='space-y-4'>
      <div className='grid gap-3 sm:grid-cols-3'>
        <StatCard
          title='用例总数'
          value={summary.total_cases}
          description={`完成 ${summary.completed_cases} · 失败 ${summary.failed_cases}`}
          icon={ListChecks}
          tone='accent-1'
        />
        <StatCard
          title='评估维度'
          value={summary.all_metrics.length}
          description='主/子维度合计'
          icon={Layers}
          tone='accent-2'
        />
        <StatCard
          title='资源数'
          value={resources.length}
          description={`设备 ${summary.devices?.length ?? 0} · API ${summary.apis?.length ?? 0}`}
          icon={MonitorSpeaker}
          tone='accent-3'
        />
      </div>

      <div className='overflow-hidden rounded-lg border'>
        <div className='overflow-x-auto'>
          <table className='w-full min-w-[560px] text-sm'>
            <thead>
              <tr className='text-muted-foreground border-b bg-muted/30'>
                <th className='px-3 py-2.5 text-left font-medium'>维度 / 资源</th>
                {resources.map((resource) => (
                  <th key={resource} className='px-3 py-2.5 text-left font-medium'>
                    {resourceLabel(resource)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.key}
                  className={
                    row.isGroupHeader
                      ? 'bg-muted/40 border-b font-semibold'
                      : 'hover:bg-muted/30 border-b'
                  }
                >
                  <td
                    className={
                      row.isGroupHeader
                        ? 'px-3 py-2 text-sm font-semibold'
                        : row.isSubDim
                          ? 'text-muted-foreground px-3 py-2 ps-8 text-sm'
                          : 'px-3 py-2 text-sm font-medium'
                    }
                  >
                    {row.name}
                  </td>
                  {resources.map((resource) => {
                    if (row.isGroupHeader) return <td key={resource} />
                    const value = getAverageValue(row.metricName, resource, metricData)
                    const unit = getMetricUnit(summary.all_metrics, row.metricName)
                    return (
                      <td key={resource} className='px-3 py-2 font-mono text-xs tabular-nums'>
                        {formatMetricForDisplay(value)}
                        {unit && <span className='text-muted-foreground ms-0.5'>{unit}</span>}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && (
          <p className='text-muted-foreground p-6 text-center text-sm'>暂无维度数据</p>
        )}
      </div>
    </div>
  )
}

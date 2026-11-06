/**
 * 对比报告家族面板（15_报告域.md §3.4，ComparisonReportPanel 对位）。
 * 报告保存卡 + 设备/API 统计 + 选择要对比的设备和 API + 两张固定对比表
 * + 分析结论 + 分组/标签对比 + 具体用例（复用）+ 二次对比差异（secondary_comparison 特有）。
 */
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import type { ReportDetailData } from '@/domain/models/report'
import { ReportChart } from '@/components/common/report-chart'
import { colorArray } from '@/application/report-view/use-report-charts'

import { ReportResourceStats } from '../report-resource-stats'
import { ReportSaveCard } from './report-save-card'
import { DeviceApiSelector } from './device-api-selector'
import { DeviceApiComparisonTable } from './device-api-comparison-table'
import { CaseExecutionComparisonTable } from './case-execution-comparison-table'
import { CaseCategoryComparison } from '../task-report-panel/case-category-comparison'
import { CaseTagComparison } from '../task-report-panel/case-tag-comparison'
import { SpecificCaseComparison } from '../task-report-panel/specific-case-comparison'
import { AnalysisEditor } from '../task-report-panel/analysis-editor'

interface ComparisonReportPanelProps {
  report: ReportDetailData
  isExporting?: boolean
  editing: boolean
  /** report:update 权限（§6 RBAC：无权限 readonly 冻结快照，隐藏编辑钮） */
  canEdit: boolean
  onStartEditing: () => void
  onExitEditing: () => void
  onSaveAnalysis: (content: string) => void
}

export function ComparisonReportPanel({
  report,
  isExporting,
  editing,
  canEdit,
  onStartEditing,
  onExitEditing,
  onSaveAnalysis,
}: ComparisonReportPanelProps) {
  const [selectedIds, setSelectedIds] = useState<Set<number>>(
    () => new Set([...((report.summary.devices ?? []).map((d) => d.id)), ...((report.summary.apis ?? []).map((a) => a.id))])
  )

  const toggleDevice = (id: number) =>
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const isSecondary = report.type === 'secondary_comparison'

  // 二次对比差异矩阵（P3-9 转置修正：行=评估维度，列=各报告；最优 text-success / 最差 text-destructive）
  const secondaryDiff = useMemo(() => {
    if (!isSecondary) return null
    const reports = report.summary.metric_data.map((g) => g.resource)
    const dimensions = report.summary.all_metrics.map((m) => m.name)
    if (reports.length === 0 || dimensions.length === 0) return null
    const valueOf = (resource: string, metric: string): number | undefined => {
      const group = report.summary.metric_data.find((g) => g.resource === resource)
      return (group?.metrics ?? []).find((m) => m.metric === metric)?.value
    }
    return { reports, dimensions, valueOf }
  }, [isSecondary, report.summary.metric_data, report.summary.all_metrics])

  return (
    <div className='space-y-6'>
      <ReportSaveCard report={report} />

      <section id='report-resource-stats' className='scroll-mt-20 space-y-3'>
        <ReportResourceStats report={report} />
        <DeviceApiSelector report={report} selectedIds={selectedIds} onToggle={toggleDevice} />
        <DeviceApiComparisonTable report={report} isExporting={isExporting} selectedIds={selectedIds} />
        <CaseExecutionComparisonTable report={report} isExporting={isExporting} selectedIds={selectedIds} />
      </section>

      <section id='report-conclusion' className='scroll-mt-20'>
        <AnalysisEditor
          title='分析结论'
          analysis={report.analysis}
          readonly={!canEdit}
          editing={editing}
          onStartEditing={onStartEditing}
          onExitEditing={onExitEditing}
          onSaveAnalysis={onSaveAnalysis}
        />
      </section>

      <section id='report-case-category' className='scroll-mt-20'>
        <CaseCategoryComparison report={report} isExporting={isExporting} />
      </section>

      <section id='report-case-tag' className='scroll-mt-20'>
        <CaseTagComparison report={report} isExporting={isExporting} />
      </section>

      <section id='report-specific-cases' className='scroll-mt-20'>
        <SpecificCaseComparison report={report} isExporting={isExporting} />
      </section>

      {isSecondary && secondaryDiff && (
        <section id='report-compare-diff' className='scroll-mt-20 space-y-3'>
          <div className='flex items-center gap-2'>
            <h3 className='text-sm font-semibold'>对比差异</h3>
            <Badge variant='outline'>二次对比</Badge>
          </div>
          <div className='overflow-x-auto rounded-lg border'>
            <table className='w-full min-w-[480px] text-sm'>
              <thead>
                <tr className='text-muted-foreground border-b bg-muted/30'>
                  <th className='px-3 py-2 text-left font-medium'>评估维度</th>
                  {secondaryDiff.reports.map((resource) => (
                    <th key={resource} className='px-3 py-2 text-left font-medium'>
                      {resource}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {secondaryDiff.dimensions.map((metric) => {
                  const values = secondaryDiff.reports.map((r) => secondaryDiff.valueOf(r, metric))
                  const numeric = values.filter((v): v is number => v !== undefined)
                  const max = numeric.length ? Math.max(...numeric) : undefined
                  const min = numeric.length ? Math.min(...numeric) : undefined
                  return (
                    <tr key={metric} className='hover:bg-muted/30 border-b last:border-0'>
                      <td className='px-3 py-2 text-sm font-medium'>{metric}</td>
                      {values.map((v, i) => (
                        <td key={i} className='px-3 py-2 font-mono text-xs tabular-nums'>
                          {v === undefined ? (
                            <span className='text-muted-foreground/50'>—</span>
                          ) : (
                            <span
                              className={
                                v === max && numeric.length > 1
                                  ? 'text-success'
                                  : v === min && numeric.length > 1
                                    ? 'text-destructive'
                                    : ''
                              }
                            >
                              {v.toFixed(2)}
                            </span>
                          )}
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {/* 趋势折线（§3.4 二次对比差异：各报告时序/维度趋势，INT-360 §4.8 保留；预测虚线 AI 搁置） */}
          <ReportChart
            title='对比趋势'
            subtitle='各报告评估维度走势'
            type='line'
            series={{
              labels: secondaryDiff.dimensions,
              datasets: secondaryDiff.reports.map((resource, i) => ({
                label: resource,
                data: secondaryDiff.dimensions.map((m) => secondaryDiff.valueOf(resource, m) ?? 0),
                borderColor: colorArray(i),
                backgroundColor: colorArray(i, 'B3'),
                fill: false,
                tension: 0.3,
              })),
            }}
            height={280}
          />
        </section>
      )}
    </div>
  )
}

/**
 * 对比报告家族面板（15_报告域.md §3.4，ComparisonReportPanel 对位）。
 * 报告保存卡 + 设备/API 统计 + 选择要对比的设备和 API + 两张固定对比表
 * + 分析结论 + 分组/标签对比 + 具体用例（复用）+ 二次对比差异（secondary_comparison 特有）。
 */
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import type { ReportDetailData } from '@/domain/models/report'

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
  onStartEditing: () => void
  onExitEditing: () => void
  onSaveAnalysis: (content: string) => void
}

export function ComparisonReportPanel({
  report,
  isExporting,
  editing,
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

  const secondaryDiff = useMemo(() => {
    if (!isSecondary) return null
    // 二次对比：行=评估维度，列=各报告；最优 text-success / 最差 text-destructive
    return report.summary.metric_data.map((group) => ({
      dimension: group.metrics.map((m) => m.metric).join(' / ') || group.resource,
      values: group.metrics.map((m) => ({ metric: m.metric, value: m.value })),
    }))
  }, [isSecondary, report.summary.metric_data])

  return (
    <div className='space-y-6'>
      <ReportSaveCard report={report} />

      <section id='report-resource-stats' className='scroll-mt-20 space-y-3'>
        <ReportResourceStats report={report} />
        <DeviceApiSelector report={report} selectedIds={selectedIds} onToggle={toggleDevice} />
        <DeviceApiComparisonTable report={report} isExporting={isExporting} />
        <CaseExecutionComparisonTable report={report} isExporting={isExporting} />
      </section>

      <section id='report-conclusion' className='scroll-mt-20'>
        <AnalysisEditor
          title='分析结论'
          analysis={report.analysis}
          readonly={false}
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
                  {secondaryDiff.map((row, i) => (
                    <th key={i} className='px-3 py-2 text-left font-medium'>
                      {row.dimension}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr className='hover:bg-muted/30 border-b last:border-0'>
                  <td className='px-3 py-2 text-sm font-medium'>指标值</td>
                  {secondaryDiff.map((row, i) => {
                    const values = row.values.map((v) => v.value)
                    const max = Math.max(...values)
                    const min = Math.min(...values)
                    return (
                      <td key={i} className='px-3 py-2 font-mono text-xs tabular-nums'>
                        {row.values.map((v) => (
                          <span
                            key={v.metric}
                            className={
                              v.value === max
                                ? 'text-success block'
                                : v.value === min
                                  ? 'text-destructive block'
                                  : 'block'
                            }
                          >
                            {v.metric}: {v.value.toFixed(2)}
                          </span>
                        ))}
                      </td>
                    )
                  })}
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}

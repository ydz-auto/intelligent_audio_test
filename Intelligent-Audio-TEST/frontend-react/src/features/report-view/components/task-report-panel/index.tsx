/**
 * 任务级报告面板（15_报告域.md §3.3，TaskReportPanel 对位）。
 * 分区顺序固定：总览 → 设备与API → 分析结论 → 对比表格（动态）→ 用例分组 → 用例标签 → 具体用例。
 */
import type { ReportDetailData } from '@/domain/models/report'

import { ReportOverviewCard } from './report-overview-card'
import { ReportResourceStats } from '../report-resource-stats'
import { AnalysisEditor } from './analysis-editor'
import { ComparisonTable } from './comparison-table'
import { CaseCategoryComparison } from './case-category-comparison'
import { CaseTagComparison } from './case-tag-comparison'
import { SpecificCaseComparison } from './specific-case-comparison'

interface TaskReportPanelProps {
  report: ReportDetailData
  isExporting?: boolean
  editing: boolean
  /** report:update 权限（§6 RBAC：无权限 readonly 冻结快照，隐藏编辑钮） */
  canEdit: boolean
  onStartEditing: () => void
  onExitEditing: () => void
  onSaveAnalysis: (content: string) => void
}

/** 对比表格稳定 key（P3：弃 index key，避免表格排序/过滤后 React 状态串用；标题+列+首行内容指纹） */
function comparisonTableKey(table: { title: string; columns: { key: string }[]; data: Record<string, unknown>[] }): string {
  const columns = table.columns.map((c) => c.key).join(',')
  const head = table.data[0] ? Object.values(table.data[0]).join('|') : ''
  return `${table.title}:${columns}:${table.data.length}:${head}`
}

export function TaskReportPanel({
  report,
  isExporting,
  editing,
  canEdit,
  onStartEditing,
  onExitEditing,
  onSaveAnalysis,
}: TaskReportPanelProps) {
  const tables = report.summary.tables ?? []

  return (
    <div className='space-y-6'>
      {/* §3.3.1 总览 */}
      <section id='report-overview' className='scroll-mt-20 space-y-3'>
        <h3 className='text-sm font-semibold'>总览</h3>
        <ReportOverviewCard report={report} />
      </section>

      {/* §3.3.2 设备与 API */}
      <section id='report-resource-stats' className='scroll-mt-20'>
        <ReportResourceStats report={report} isExporting={isExporting} />
      </section>

      {/* §3.3.3 分析结论 */}
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

      {/* §3.3.4 对比表格（动态） */}
      {tables.length > 0 && (
        <section id='report-comparison-tables' className='scroll-mt-20 space-y-3'>
          <h3 className='text-sm font-semibold'>对比表格</h3>
          {tables.map((table) => (
            <ComparisonTable key={comparisonTableKey(table)} table={table} isExporting={isExporting} />
          ))}
        </section>
      )}

      {/* §3.3.5 按用例分组对比 */}
      <section id='report-case-category' className='scroll-mt-20'>
        <CaseCategoryComparison report={report} isExporting={isExporting} />
      </section>

      {/* §3.3.6 按用例标签对比 */}
      <section id='report-case-tag' className='scroll-mt-20'>
        <CaseTagComparison report={report} isExporting={isExporting} />
      </section>

      {/* §3.3.7 具体用例 */}
      <section id='report-specific-cases' className='scroll-mt-20'>
        <SpecificCaseComparison report={report} isExporting={isExporting} />
      </section>
    </div>
  )
}

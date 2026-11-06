/**
 * 用例执行数量对比表（15_报告域.md §3.4，ComparisonTable title="用例执行数量对比"）。
 * 列：name/total/executed/completed/failed/successRate/failedRate。
 * selectedIds：设备/API 选择器选中集合——行数据按选中资源过滤（§3.4 多被测主体挑选语义）。
 */
import type { ReportDetailData } from '@/domain/models/report'

import { ComparisonTable } from '../task-report-panel/comparison-table'

export function CaseExecutionComparisonTable({
  report,
  isExporting,
  selectedIds,
}: {
  report: ReportDetailData
  isExporting?: boolean
  selectedIds?: Set<number>
}) {
  const rows = [
    ...(report.summary.device_stats ?? []).map((d) => ({
      id: d.id,
      name: d.name,
      total: d.total_cases,
      executed: d.completed_cases + d.failed_cases,
      completed: d.completed_cases,
      failed: d.failed_cases,
      successRate: d.success_rate,
      failedRate: d.total_cases > 0 ? (d.failed_cases / d.total_cases) * 100 : 0,
    })),
    ...(report.summary.api_stats ?? []).map((a) => ({
      id: a.id,
      name: a.name,
      total: a.total_cases,
      executed: a.completed_cases + a.failed_cases,
      completed: a.completed_cases,
      failed: a.failed_cases,
      successRate: a.success_rate,
      failedRate: a.total_cases > 0 ? (a.failed_cases / a.total_cases) * 100 : 0,
    })),
  ].filter(
    (row) =>
      !selectedIds || selectedIds.size === 0 || selectedIds.has(row.id)
  )

  return (
    <ComparisonTable
      table={{
        title: '用例执行数量对比',
        default_collapsed: true,
        columns: [
          { key: 'name', label: '名称' },
          { key: 'total', label: '总数', type: 'number' },
          { key: 'executed', label: '已执行', type: 'number' },
          { key: 'completed', label: '完成', type: 'number' },
          { key: 'failed', label: '失败', type: 'number' },
          { key: 'successRate', label: '成功率', type: 'percentage' },
          { key: 'failedRate', label: '失败率', type: 'percentage' },
        ],
        data: rows,
      }}
      isExporting={isExporting}
    />
  )
}

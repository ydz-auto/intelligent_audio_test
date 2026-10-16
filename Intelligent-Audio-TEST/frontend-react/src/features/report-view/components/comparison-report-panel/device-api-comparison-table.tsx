/**
 * 设备/API 信息对比表（15_报告域.md §3.4，ComparisonTable title="设备/API信息对比"）。
 * 列：name/type/version/status/totalCases/successRate/avgResponseTime/stability。
 */
import type { ReportDetailData } from '@/domain/models/report'

import { ComparisonTable } from '../task-report-panel/comparison-table'

export function DeviceApiComparisonTable({ report, isExporting }: { report: ReportDetailData; isExporting?: boolean }) {
  const rows = [
    ...(report.summary.device_stats ?? []).map((d) => ({
      name: d.name,
      type: '设备',
      version: d.model ?? '—',
      status: d.status ?? 'offline',
      totalCases: d.total_cases,
      successRate: d.success_rate,
      avgResponseTime: (d.metrics?.['平均响应时间'] as number) ?? '—',
      stability: (d.metrics?.['稳定性'] as number) ?? '—',
    })),
    ...(report.summary.api_stats ?? []).map((a) => ({
      name: a.name,
      type: 'API',
      version: 'v',
      status: a.status ?? 'offline',
      totalCases: a.total_cases,
      successRate: a.success_rate,
      avgResponseTime: a.avg_response_time ?? '—',
      stability: a.stability ?? '—',
    })),
  ]

  return (
    <ComparisonTable
      table={{
        title: '设备/API信息对比',
        default_collapsed: true,
        columns: [
          { key: 'name', label: '名称' },
          { key: 'type', label: '类型' },
          { key: 'version', label: '版本' },
          { key: 'status', label: '状态', type: 'status' },
          { key: 'totalCases', label: '用例数', type: 'number' },
          { key: 'successRate', label: '成功率', type: 'percentage' },
          { key: 'avgResponseTime', label: '平均响应时间', type: 'number' },
          { key: 'stability', label: '稳定性', type: 'number' },
        ],
        data: rows,
      }}
      isExporting={isExporting}
    />
  )
}

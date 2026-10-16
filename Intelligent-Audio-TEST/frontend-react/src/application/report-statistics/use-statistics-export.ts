/**
 * 统计结果/报表生成导出（application 层；15_报告域.md §2.2「统计结果导出」+ §4.3 导出链路复用）。
 * 统计报表导出复用报告导出 Dialog 的 format 语义（CSV/Excel/PDF/HTML）；mock 出 Blob 下载（红线④）。
 */
import { useCallback } from 'react'
import { toast } from 'sonner'

export type StatisticsExportFormat = 'csv' | 'excel' | 'pdf' | 'html'

export function useStatisticsExport() {
  const exportStatistics = useCallback(
    (format: StatisticsExportFormat, scope: string) => {
      // TODO(API 接线): 复用报告导出链路（POST /reports/export 同源），当前 mock Blob 下载
      const blob = new Blob([`${scope} 统计分析结果（${format}）\nmock 数据，待 API 接线。`], {
        type: 'text/plain;charset=utf-8',
      })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `统计结果-${Date.now()}.${format === 'excel' ? 'xlsx' : format}`
      link.click()
      URL.revokeObjectURL(url)
      toast.success('统计报告已导出')
    },
    []
  )

  return { exportStatistics }
}

/**
 * 统计结果/报表生成导出（application 层；15_报告域.md §2.2「统计结果导出」+ §4.3 导出链路复用）。
 * INT-1547 P2-5：统计报表导出复用报告导出链路（POST /reports/export，ids=统计范围内报告），
 * 由后端生成文件，前端不再本地拼 mock Blob（红线④）。
 */
import { useCallback, useState } from 'react'
import { toast } from 'sonner'

import { ApiError } from '@/infrastructure/api/api-error'
import { exportReports } from '@/infrastructure/api/reports-api'

export type StatisticsExportFormat = 'csv' | 'excel' | 'pdf' | 'html'

export interface StatisticsExportPayload {
  format: StatisticsExportFormat
  /** 导出范围说明（报表名称 / 统计维度），用于文件名与提示 */
  name: string
  /** 统计范围内报告 id（POST /reports/export 的 ids） */
  ids: number[]
}

function extensionOf(format: StatisticsExportFormat): string {
  return format === 'excel' ? 'xlsx' : format
}

/** 文件名非法字符收敛（Windows/macOS 双兼容；报表名称来自用户输入） */
function sanitizeFilename(name: string): string {
  return name.replace(/[\\/:*?"<>|]/g, '_').trim() || '统计结果'
}

function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export function useStatisticsExport() {
  const [exporting, setExporting] = useState(false)

  const exportStatistics = useCallback(async (payload: StatisticsExportPayload) => {
    const { format, name, ids } = payload
    if (ids.length === 0) {
      toast.error('当前统计范围内没有可导出的报告')
      return
    }
    setExporting(true)
    try {
      const blob = await exportReports({ ids, format })
      triggerBlobDownload(blob, `${sanitizeFilename(name)}.${extensionOf(format)}`)
      toast.success('统计结果已导出')
    } catch (err) {
      toast.error(err instanceof ApiError && err.userMessage ? err.userMessage : '统计结果导出失败，请重试')
    } finally {
      setExporting(false)
    }
  }, [])

  return { exportStatistics, exporting }
}

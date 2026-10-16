/**
 * 分析结论加载/保存（application 层，15_报告域.md §3.3.3）。
 * sanitizeConclusion 清洗（去危险 HTML）后渲染；保存 → PUT /reports/{id} 的 analysis
 * （V9.7.31 ReportView 实测同时写 summary.analysisConclusion + conclusion 双写兼容）。
 */
import { useCallback, useMemo } from 'react'
import { toast } from 'sonner'

import { updateReport } from '@/infrastructure/api/reports-api'

/** 结论清洗（保留换行/列表，剥离脚本与危险标签） */
export function sanitizeConclusion(html: string | undefined): string {
  if (!html) return ''
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/on\w+="[^"]*"/gi, '')
}

/** 结论标签默认池（AnalysisEditor 可选区；默认折叠） */
export const DEFAULT_CONCLUSION_TAGS = [
  '性能优化',
  '功能改进',
  '稳定性问题',
  '兼容性问题',
  '建议改进',
]

export function useReportAnalysis(reportId: number, currentAnalysis?: string) {
  const hasAnalysis = useMemo(
    () => Boolean(currentAnalysis && sanitizeConclusion(currentAnalysis).trim()),
    [currentAnalysis]
  )

  const saveConclusion = useCallback(
    async (content: string) => {
      await updateReport(reportId, { analysis: content })
      toast.success('结论保存成功')
    },
    [reportId]
  )

  const saveReport = useCallback(
    async (payload: { name?: string; description?: string; analysis?: string }) => {
      await updateReport(reportId, payload)
      toast.success('报告保存成功')
    },
    [reportId]
  )

  return { hasAnalysis, saveConclusion, saveReport }
}

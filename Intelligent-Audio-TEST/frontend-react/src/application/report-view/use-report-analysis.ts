/**
 * 分析结论加载/保存（application 层，15_报告域.md §3.3.3）。
 * 结论为纯文本字段：展示走 React 文本渲染（自动转义，杜绝存储型 XSS，P1-1 审计修复），
 * 无 HTML 清洗层；保存 → PUT /reports/{id} 的 analysis
 * （V9.7.31 ReportView 实测同时写 summary.analysisConclusion + conclusion 双写兼容）。
 */
import { useCallback, useMemo } from 'react'
import { toast } from 'sonner'

import { updateReport } from '@/infrastructure/api/reports-api'

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
    () => Boolean(currentAnalysis && currentAnalysis.trim()),
    [currentAnalysis]
  )

  const saveConclusion = useCallback(
    async (content: string) => {
      // V9.7.31 ReportView 实测双写：PUT /reports/{id} 的 analysis + summary.analysisConclusion/conclusion
      await updateReport(reportId, {
        analysis: content,
        summary: { analysisConclusion: content, conclusion: content },
      })
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

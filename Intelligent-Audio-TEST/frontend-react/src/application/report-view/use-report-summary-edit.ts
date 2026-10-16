/**
 * 摘要编辑防抖保存（application 层，15_报告域.md §3.6）。
 * 分组/标签重命名 → scheduleSaveSummary 200ms 防抖 → PUT /reports/{id} 的
 * summary.caseCategories/allCaseTags/allTags/resourceHeaders 白名单。
 */
import { useCallback, useRef } from 'react'
import { toast } from 'sonner'

import { updateReport } from '@/infrastructure/api/reports-api'
import type { ReportSummaryUpdate } from '@/domain/models/report'

export function useReportSummaryEdit(reportId: number) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const payloadRef = useRef<ReportSummaryUpdate>({})

  const scheduleSaveSummary = useCallback(
    (patch: ReportSummaryUpdate) => {
      payloadRef.current = { ...payloadRef.current, ...patch }
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        void updateReport(reportId, { summary: payloadRef.current } as never)
          .then(() => toast.success('报告保存成功'))
          .catch(() => toast.error('报告保存失败'))
        payloadRef.current = {}
      }, 200)
    },
    [reportId]
  )

  return { scheduleSaveSummary }
}

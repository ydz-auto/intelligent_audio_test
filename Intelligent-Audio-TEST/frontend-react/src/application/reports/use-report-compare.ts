/**
 * 报告对比/二次对比（application 层，INT-434 P2-20 收敛）。
 * 基于任务（compareReports）与基于已选报告（secondaryCompareReports）双通道，
 * 页面与 Dialog 不直 import infrastructure API。
 */
import { useCallback } from 'react'
import { toast } from 'sonner'

import {
  compareReports,
  secondaryCompareReports,
} from '@/infrastructure/api/reports-api'

export function useReportCompare() {
  const compare = useCallback(
    async (taskIds: number[], name?: string): Promise<number> => {
      const result = await compareReports({ task_ids: taskIds, name: name || '对比报告' })
      toast.success('对比报告已生成')
      return result.report_id
    },
    []
  )

  const secondaryCompare = useCallback(
    async (reportIds: number[], description?: string): Promise<number> => {
      const result = await secondaryCompareReports({
        report_ids: reportIds,
        description: description || undefined,
      })
      toast.success('二次对比报告已生成')
      return result.report_id
    },
    []
  )

  return { compare, secondaryCompare }
}

/**
 * 摘要编辑防抖保存（application 层，15_报告域.md §3.6）。
 * 分组/标签重命名 → scheduleSaveSummary 200ms 防抖 → PUT /reports/{id} 的
 * summary.caseCategories/allCaseTags/allTags/resourceHeaders 白名单。
 * P2-4：顶层浅合并改为按稳定标识键深合并（200ms 窗口内连续多次重命名互不覆盖）；
 * PUT 经队列串行化（前序请求 resolve 后才发下一批），消除在途 PUT 竞态。
 */
import { useCallback, useRef } from 'react'
import { toast } from 'sonner'

import { updateReport } from '@/infrastructure/api/reports-api'
import type { ReportSummaryUpdate } from '@/domain/models/report'

/** 数组类摘要字段的稳定标识键（category_id / tag_id / key 优先，name 兜底） */
function summaryArrayKey(item: Record<string, unknown>): string {
  const id = item.category_id ?? item.tag_id ?? item.key
  if (typeof id === 'string' && id) return id
  const name = item.category_name ?? item.tag_name ?? item.label ?? item.name
  return typeof name === 'string' ? name : JSON.stringify(item)
}

/** 按标识键深合并数组（later 同名条目覆盖，其余保留） */
function mergeArray<T>(base: T[] | undefined, patch: T[] | undefined): T[] | undefined {
  if (!base) return patch
  if (!patch) return base
  const map = new Map<string, T>()
  for (const item of base) map.set(summaryArrayKey(item as unknown as Record<string, unknown>), item)
  for (const item of patch) map.set(summaryArrayKey(item as unknown as Record<string, unknown>), item)
  return [...map.values()]
}

/** 深合并（数组字段按标识键合并，避免后者整体覆盖前者丢更新） */
function mergeSummaryUpdate(
  base: ReportSummaryUpdate,
  patch: ReportSummaryUpdate
): ReportSummaryUpdate {
  return {
    ...base,
    ...patch,
    caseCategories: mergeArray(base.caseCategories, patch.caseCategories),
    allCaseTags: mergeArray(base.allCaseTags, patch.allCaseTags),
    allTags: mergeArray(base.allTags, patch.allTags),
    resourceHeaders: mergeArray(base.resourceHeaders, patch.resourceHeaders),
  }
}

export function useReportSummaryEdit(reportId: number) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const payloadRef = useRef<ReportSummaryUpdate>({})
  // PUT 串行化队列：前序请求 resolve 后才发下一批，避免在途 PUT 竞态丢更新
  const pendingRef = useRef<Promise<unknown>>(Promise.resolve())

  const scheduleSaveSummary = useCallback(
    (patch: ReportSummaryUpdate) => {
      payloadRef.current = mergeSummaryUpdate(payloadRef.current, patch)
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        const payload = payloadRef.current
        payloadRef.current = {}
        if (Object.keys(payload).length === 0) return
        pendingRef.current = pendingRef.current
          .catch(() => {})
          .then(() => updateReport(reportId, { summary: payload } as never))
          .then(() => toast.success('报告保存成功'))
          .catch(() => toast.error('报告保存失败'))
      }, 200)
    },
    [reportId]
  )

  return { scheduleSaveSummary }
}

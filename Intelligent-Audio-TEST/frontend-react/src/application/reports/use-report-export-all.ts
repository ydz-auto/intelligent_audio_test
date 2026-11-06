/**
 * 导出「当前筛选全部」报告 id 获取（application 层，15_报告域.md §2 导出范围口径）。
 * P2-2：管理页导出「全部报告」范围需含当前筛选全量 id（非仅当前页 items）；
 * 服务端分页语义：per_page=1000 一次性拉全量过滤结果（与 fetchReportTypeCounts 同口径），
 * 再交由 exportReports 导出。TODO(API 接线): 后端支持传查询条件导出后移除全量拉取。
 */
import { useCallback } from 'react'

import type { ReportListQuery } from '@/domain/models/report'
import { fetchReportList } from '@/infrastructure/api/reports-api'

export function useReportExportAll() {
  return useCallback(async (query: ReportListQuery): Promise<number[]> => {
    const data = await fetchReportList({ ...query, page: 1, per_page: 1000 })
    return data.items.map((i) => i.id)
  }, [])
}

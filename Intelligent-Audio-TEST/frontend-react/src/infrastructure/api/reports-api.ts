/**
 * reports 域 API 桩（infrastructure 层；红线④：一律 mock，不接真实后端）。
 * TODO(API 接线): 替换为真实请求 —— 端点对照 api_gateway/routes/report_bp.py 实测：
 *   GET  /reports                        （report:read，ReportListQuery 全参，服务端分页）
 *   GET  /reports/tab-counts             （report:read，{all,draft,published,comparison}）
 *   GET  /reports/{id}                   （report:read，ReportDetailData）
 *   GET  /reports/{id}/cases             （report:read，ReportCaseListQuery）
 *   POST /reports/{id}/cases/search      （report:read 语义，ReportSearchCasesRequest 全参）
 * 收藏/回收站端点（favorite_trash_bp.py:110-135，INT-215 口径）：
 *   POST/DELETE /reports/{report_id}/favorite、POST /reports/{report_id}/restore、
 *   POST /reports/restore（批量）、DELETE /reports/{report_id}/purge、POST /reports/purge（批量）。
 */
import type {
  ReportCaseListData,
  ReportCaseItem,
  ReportDetailData,
  ReportListData,
  ReportListItem,
  ReportListQuery,
  ReportSearchCasesRequest,
  ReportTabCounts,
} from '@/domain/models/report'

import {
  MOCK_REPORT_CASE_LIST_DATA,
  MOCK_REPORT_DETAILS,
  MOCK_REPORT_LIST_ITEMS,
  MOCK_REPORT_TAB_COUNTS,
} from '../mock/reports-mock'
import { resolveReportUiFlags } from '../stores/reports-ui-store'

/** 按 ReportListQuery 过滤/排序/分页 mock 列表（服务端分页语义平移，manualPagination 直用） */
export async function fetchReportList(
  query: ReportListQuery
): Promise<ReportListData> {
  const { page, per_page, report_type, status, keyword, start_time, end_time, algorithm_type, sort_by, order, favorite, deleted } =
    query
  const pageSize = per_page ?? 20

  let items = MOCK_REPORT_LIST_ITEMS.filter((item) => {
    if (report_type && item.type !== report_type) return false
    if (status && item.status !== status) return false
    if (keyword) {
      const kw = keyword.toLowerCase()
      if (
        !item.name.toLowerCase().includes(kw) &&
        !item.task_name.toLowerCase().includes(kw) &&
        !(item.algorithm_type ?? '').toLowerCase().includes(kw)
      ) {
        return false
      }
    }
    if (algorithm_type && item.algorithm_type !== algorithm_type) return false
    // 演示态覆盖（收藏/软删/彻底删除经 store 生效）；回收站态与正常态互斥
    const flags = resolveReportUiFlags(item.id, item.is_favorite)
    if (deleted) {
      if (!flags.deleted) return false
    } else {
      if (flags.deleted) return false
      if (favorite && !flags.isFavorite) return false
    }
    if (start_time && item.created_at < start_time) return false
    if (end_time && item.created_at > end_time) return false
    return true
  })

  const sortValue = (item: ReportListItem): string | number => {
    switch (sort_by) {
      case 'name':
        return item.name
      case 'pass_rate':
        return item.summary.pass_rate
      case 'total_cases':
        return item.summary.total_cases
      default:
        return item.created_at
    }
  }
  items = [...items].sort((a, b) => {
    const cmp = String(sortValue(a)).localeCompare(String(sortValue(b)))
    return order === 'asc' ? cmp : -cmp
  })

  const total = items.length
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const start = (page - 1) * pageSize
  return {
    items: items.slice(start, start + pageSize).map((item) => {
      const flags = resolveReportUiFlags(item.id, item.is_favorite)
      return { ...item, is_favorite: flags.isFavorite, deleted: flags.deleted }
    }),
    total,
    page,
    per_page: pageSize,
    pages,
  }
}

export async function fetchReportTabCounts(): Promise<ReportTabCounts> {
  return MOCK_REPORT_TAB_COUNTS
}

export async function fetchReportDetail(
  reportId: number
): Promise<ReportDetailData> {
  return MOCK_REPORT_DETAILS[reportId] ?? MOCK_REPORT_DETAILS[1201]
}

export async function fetchReportCases(
  _reportId: number,
  _query: ReportSearchCasesRequest
): Promise<ReportCaseListData> {
  return MOCK_REPORT_CASE_LIST_DATA
}

/** 用例 metrics 键提取（dict {resource:{metric}} 与 list [{resource,metrics}] 双格式） */
function caseMetricKeys(item: ReportCaseItem): string[] {
  if (Array.isArray(item.metrics)) {
    return item.metrics.flatMap((g) => g.metrics.map((m) => m.metric))
  }
  const keys = new Set<string>()
  for (const resourceMetrics of Object.values(item.metrics)) {
    for (const key of Object.keys(resourceMetrics)) keys.add(key)
  }
  return [...keys]
}

/** 具体用例筛选 mock（按 keyword/分组/标签/指标过滤 + 排序；页面演示用） */
export async function searchReportCases(
  _reportId: number,
  query: ReportSearchCasesRequest
): Promise<ReportCaseListData> {
  let items: ReportCaseItem[] = MOCK_REPORT_CASE_LIST_DATA.items
  if (query.keyword) {
    const kw = query.keyword.toLowerCase()
    items = items.filter(
      (c) =>
        c.name.toLowerCase().includes(kw) ||
        c.id.toLowerCase().includes(kw) ||
        (c.description ?? '').toLowerCase().includes(kw)
    )
  }
  if (query.categories?.length) {
    items = items.filter((c) => query.categories?.includes(c.category ?? ''))
  }
  if (query.tags?.length) {
    items = items.filter((c) => c.tags.some((t) => query.tags?.includes(t)))
  }
  if (query.metrics?.length) {
    items = items.filter((c) =>
      caseMetricKeys(c).some((m) => query.metrics?.includes(m))
    )
  }
  if (query.sort_by && query.sort_by !== 'name') {
    const dir = query.sort_order === 'asc' ? 1 : -1
    items = [...items].sort((a, b) => {
      if (query.sort_by === 'category') {
        return (a.category ?? '').localeCompare(b.category ?? '') * dir
      }
      if (query.sort_by === 'createdat') {
        return a.id.localeCompare(b.id) * dir
      }
      if (query.sort_by === 'metric' && query.sort_metric) {
        const av = readCaseMetric(items.find((i) => i.id === a.id) ?? a, query.sort_metric, query.sort_resource)
        const bv = readCaseMetric(items.find((i) => i.id === b.id) ?? b, query.sort_metric, query.sort_resource)
        return ((av ?? 0) - (bv ?? 0)) * dir
      }
      return 0
    })
  } else {
    items = [...items].sort((a, b) =>
      query.sort_order === 'asc' ? a.name.localeCompare(b.name) : b.name.localeCompare(a.name)
    )
  }
  const pageSize = query.per_page || 20
  const total = items.length
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const start = (query.page - 1) * pageSize
  return { items: items.slice(start, start + pageSize), total, page: query.page, per_page: pageSize, pages }
}

/** 读取用例单指标值（dict/list 双格式；resource 缺省取首个） */
function readCaseMetric(
  item: ReportCaseItem,
  metric: string,
  resource?: string
): number | undefined {
  if (Array.isArray(item.metrics)) {
    const group = item.metrics.find((g) => !resource || g.resource === resource)
    return group?.metrics.find((m) => m.metric === metric)?.value
  }
  const entries = Object.entries(item.metrics)
  const target = resource ? (item.metrics[resource] ?? {}) : (entries[0]?.[1] ?? {})
  return target[metric]
}

/** GET /reports/{id}/cases/{caseId}/logs/download（logs.zip Blob；红线圈：mock 空数据演示） */
export async function downloadCaseLogs(
  _reportId: number,
  _caseId: string
): Promise<{ blob: Blob; size: number }> {
  const blob = new Blob(['mock logs'], { type: 'application/zip' })
  return { blob, size: blob.size }
}

/** POST /reports/case-averages（按任务筛选用例平均值；task_id 路径 mock 演示） */
export async function getCaseAverages(
  _taskId: number,
  _filters: { tags?: string[]; categories?: string[]; includeUntagged?: boolean }
): Promise<Record<string, number>> {
  return { 唤醒成功率: 95.8, 识别准确率: 93.1 }
}

// ---------------------------------------------------------------------------
// 变更类 API 桩（出图先：resolve 空数据，页面以乐观本地状态 + toast 演示；
// TODO(API 接线): 接入真实端点后移除本地乐观状态，改 invalidate 重拉）
// ---------------------------------------------------------------------------

export async function updateReport(
  _reportId: number,
  _payload: { name?: string; description?: string; analysis?: string }
): Promise<{ success: boolean }> {
  return { success: true }
}

export async function publishReport(_reportId: number): Promise<{ success: boolean }> {
  return { success: true }
}

export async function deleteReport(_reportId: number): Promise<{ success: boolean }> {
  return { success: true }
}

export async function batchDeleteReports(_ids: number[]): Promise<{ success: boolean }> {
  return { success: true }
}

export async function regenerateReport(_reportId: number): Promise<{ success: boolean }> {
  return { success: true }
}

export async function generateTaskReport(_payload: {
  task_id: number
  name?: string
  description?: string
}): Promise<{ report_id: number }> {
  return { report_id: 1201 }
}

export async function compareReports(_payload: {
  task_ids: number[]
  name?: string
  description?: string
}): Promise<{ report_id: number }> {
  return { report_id: 1190 }
}

export async function secondaryCompareReports(_payload: {
  report_ids: number[]
  description?: string
}): Promise<{ report_id: number }> {
  return { report_id: 1188 }
}

export async function exportReports(_payload: {
  ids: number[]
  format: string
}): Promise<{ success: boolean }> {
  return { success: true }
}

export async function toggleReportFavorite(_reportId: number): Promise<{ success: boolean }> {
  return { success: true }
}

export async function restoreReport(_reportId: number): Promise<{ success: boolean }> {
  return { success: true }
}

export async function purgeReport(_reportId: number): Promise<{ success: boolean }> {
  return { success: true }
}

export async function fetchReportProgress(_reportId: number): Promise<{
  status: 'pending' | 'generating' | 'completed' | 'failed'
  progress: number
}> {
  return { status: 'generating', progress: 60 }
}

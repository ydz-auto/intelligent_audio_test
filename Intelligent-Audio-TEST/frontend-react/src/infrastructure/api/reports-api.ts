/**
 * reports 域 API 桩（infrastructure 层；红线④：一律 mock，不接真实后端）。
 * TODO(API 接线): 替换为真实请求 —— 端点对照 api_gateway/routes/report_bp.py 实测：
 *   GET  /reports                        （report:read，ReportListQuery 全参，服务端分页）
 *   GET  /reports/tab-counts             （report:read，{all,draft,published,comparison}，页签取消后保留为全量分类计数）
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
  ReportCounts,
  ReportDetailData,
  ReportListData,
  ReportListItem,
  ReportListQuery,
  ReportSearchCasesRequest,
  ReportType,
} from '@/domain/models/report'

import {
  MOCK_COMPLETED_TASKS,
  MOCK_REPORT_ADVANCED_META,
  MOCK_REPORT_CASE_LIST_DATA,
  MOCK_REPORT_COUNTS,
  MOCK_REPORT_DETAILS,
  MOCK_REPORT_LIST_ITEMS,
  getReportDetailMock,
} from '../mock/reports-mock'
import { resolveReportUiFlags } from '../stores/reports-ui-store'

/** 按 ReportListQuery 过滤/排序/分页 mock 列表（服务端分页语义平移，manualPagination 直用） */
export async function fetchReportList(
  query: ReportListQuery
): Promise<ReportListData> {
  const { page, per_page, report_type, status, keyword, task_type, device_type, creator, start_time, end_time, algorithm_type, sort_by, order, favorite, deleted } =
    query
  const pageSize = per_page ?? 20

  let items = MOCK_REPORT_LIST_ITEMS.filter((item) => {
    if (report_type && item.type !== report_type) return false
    if (status && item.status !== status) return false
    // 高级搜索：任务类型/设备类型/创建者（§2 :186-188；mock 元信息按 id 合并）
    const adv = MOCK_REPORT_ADVANCED_META[item.id]
    if (task_type && adv?.task_type !== task_type) return false
    if (device_type && adv?.device_type !== device_type) return false
    if (creator && adv?.creator !== creator) return false
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
    // 演示态覆盖（收藏/软删/彻底删除经 store 生效）；回收站态与正常态互斥。
    // P2-3：store 的 restore/purge 集合优先于 mock 原值 deleted（base 软删行可恢复/彻底删除）。
    const flags = resolveReportUiFlags(item.id, item.is_favorite, item.deleted === true)
    if (deleted) {
      if (flags.purged) return false
      if (!flags.deleted) return false
    } else {
      if (flags.purged || flags.deleted) return false
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
  // P2-1 数值排序：pass_rate/total_cases 走数值减法；name/created_at 走字典序（ISO 时间串字典序=时间序）
  const cmpValue = (a: ReportListItem, b: ReportListItem): number => {
    const av = sortValue(a)
    const bv = sortValue(b)
    if (typeof av === 'number' && typeof bv === 'number') return av - bv
    return String(av).localeCompare(String(bv))
  }
  items = [...items].sort((a, b) => {
    const cmp = cmpValue(a, b)
    return order === 'asc' ? cmp : -cmp
  })

  const total = items.length
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const start = (page - 1) * pageSize
  return {
    items: items.slice(start, start + pageSize).map((item) => {
      const flags = resolveReportUiFlags(item.id, item.is_favorite, item.deleted === true)
      const adv = MOCK_REPORT_ADVANCED_META[item.id]
      return {
        ...item,
        ...adv,
        is_favorite: flags.isFavorite,
        deleted: flags.deleted,
      }
    }),
    total,
    page,
    per_page: pageSize,
    pages,
  }
}

/** 全量报告分类计数（口径修正 2026-10-16：页签取消后保留为单一列表筛选 chips/徽章行计数源） */
export async function fetchReportCounts(): Promise<ReportCounts> {
  return MOCK_REPORT_COUNTS
}

/** GET /tasks 已完成子集（生成/对比 Dialog 任务选择器数据源；mock 只读） */
export async function fetchCompletedTasks(): Promise<typeof MOCK_COMPLETED_TASKS> {
  return MOCK_COMPLETED_TASKS
}

/** Hero 类型 chips / 收藏计数（全量非回收站项；mock 常量经 API 桩消费，避免页面直 import mock） */
export async function fetchReportTypeCounts(): Promise<{
  typeCounts: Record<ReportType | 'all', number>
  favoriteCount: number
}> {
  const data = await fetchReportList({
    page: 1,
    per_page: 1000,
    sort_by: 'created_at',
    order: 'desc',
    favorite: false,
    deleted: false,
  })
  const items = data.items
  return {
    typeCounts: {
      all: items.length,
      task: items.filter((i) => i.type === 'task').length,
      comparison: items.filter((i) => i.type === 'comparison').length,
      secondary_comparison: items.filter((i) => i.type === 'secondary_comparison').length,
      benchmark: items.filter((i) => i.type === 'benchmark').length,
    },
    favoriteCount: items.filter((i) => i.is_favorite).length,
  }
}

export async function fetchReportDetail(
  reportId: number
): Promise<ReportDetailData> {
  // INT-503：列表全部 ID 均可达——富详情优先，其余按列表项参数化生成；未知 id 仍走 404 语义
  const detail = getReportDetailMock(reportId) ?? MOCK_REPORT_DETAILS[reportId]
  if (!detail) {
    // 未知 id → 404 语义（INT-434 P2-5：错误态需可达，不得静默回退 1201）
    throw new Error(`报告 ${reportId} 不存在`)
  }
  return detail
}

/**
 * Benchmark 报告列表（INT-500 v2.9：列表并入报告中心类型筛选，report_type='benchmark' 统一走 /reports 列表；
 * 本桩保留后端独立端点形态，供接线替换）。TODO(API 接线): GET /api/v1/benchmarks/reports。
 */
export async function fetchBenchmarkReports(): Promise<ReportListData> {
  return fetchReportList({
    page: 1,
    per_page: 100,
    report_type: 'benchmark',
    sort_by: 'created_at',
    order: 'desc',
    favorite: false,
    deleted: false,
  })
}

/** 发布 Benchmark 报告（§3.8；排行区块「发布 Benchmark 报告」→ POST /api/v1/benchmarks/reports）。TODO(API 接线)。 */
export async function publishBenchmarkReport(): Promise<{ reportId: number }> {
  // mock：返回 1185 关联 id（演示态）
  return { reportId: 1185 }
}

/** 用例 metrics 键提取（dict {resource:{metric}} 与 list [{resource,metrics}] 双格式） */
function caseMetricKeys(item: ReportCaseItem): string[] {
  if (Array.isArray(item.metrics)) {
    return item.metrics.flatMap((g) => (g.metrics ?? []).map((m) => m.metric))
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
    return group?.metrics?.find((m) => m.metric === metric)?.value
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

// ---------------------------------------------------------------------------
// 变更类 API 桩（出图先：resolve 空数据，页面以乐观本地状态 + toast 演示；
// TODO(API 接线): 接入真实端点后移除本地乐观状态，改 invalidate 重拉）
// ---------------------------------------------------------------------------

export async function updateReport(
  _reportId: number,
  _payload: {
    name?: string
    description?: string
    analysis?: string
    summary?: { analysisConclusion?: string; conclusion?: string }
  }
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

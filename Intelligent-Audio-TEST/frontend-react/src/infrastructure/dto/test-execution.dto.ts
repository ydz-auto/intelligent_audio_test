/**
 * 测试执行域 DTO（infrastructure/dto 层——snake_case 唯一出现层；10_测试执行.md §9）。
 * 端点对照 api_gateway/routes 实测：testcase_bp.py（GET/POST /testcases、POST /testcases/ids、
 * GET /testcases/tags）、group_bp.py（GET /groups）、task_bp.py（POST /tasks、POST /tasks/{id}/start）、
 * log_bp.py（GET /logs）、api_bp.py（GET /apis、POST /apis/{id}/health）、algorithm_bp.py（GET /algorithm/options）。
 * 设备/被测 API/用例详情复用 device.dto / apis.dto / testcase.dto 既有 DTO。
 */

/** POST /testcases/ids 全量圈定响应（testcase_bp.py:72；{ ids: [...] }） */
export interface TestCaseIdsResultDto {
  ids: string[]
  total?: number
}

/** GET /testcases/tags 分页信封（TagListData；items 为名称字符串） */
export interface TestCaseTagListDataDto {
  items: string[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** GET /groups 列表项（group.py GroupItem；分组 facet value/label 来源） */
export interface GroupItemDto {
  id: string
  name: string
  description: string | null
  algorithm_type: string | null
  created_at: string
  updated_at: string
  test_case_count: number
}

/** GET /groups 分页信封（GroupListData） */
export interface GroupListDataDto {
  items: GroupItemDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** GET /logs 列表项（log.py LogItem；业务执行日志） */
export interface LogItemDto {
  id: number
  time: string
  level: string
  category: string
  module: string
  source: string
  content: string
  task_id: number | null
  test_case_id: string | null
}

/** GET /logs 分页信封（LogListData） */
export interface LogListDataDto {
  items: LogItemDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** POST /tasks/{id}/start 响应（task.py TaskStartData；消费方只 await 不读字段） */
export interface TaskStartDataDto {
  task_id: string
  start_time?: unknown
  status: string
  expected_total_time?: number | null
  expected_complete_time?: string | null
}

/** 分组列表 → {value, label}[]（分组 facet 消费） */
export function toGroupFacetOptions(
  dto: GroupListDataDto | null | undefined
): Array<{ value: string; label: string }> {
  return (dto?.items ?? []).map((item) => ({
    value: item.id,
    label: item.name ?? item.id,
  }))
}

/** 日志列表 → 执行日志行（timestamp/message 字段收敛） */
export function toLogItems(
  dto: LogListDataDto | null | undefined
): {
  items: Array<{ id: number; timestamp: string; level: 'info' | 'warn' | 'error'; message: string }>
  total: number
  page: number
} {
  const items = (dto?.items ?? []).map((item) => ({
    id: item.id,
    timestamp: item.time ?? '',
    level: normalizeLogLevel(item.level),
    message: item.content ?? '',
  }))
  return { items, total: dto?.total ?? items.length, page: dto?.page ?? 1 }
}

/** 后端日志级别收敛为 info/warn/error 三档（warn=warning，error=error，其余 info） */
function normalizeLogLevel(level: string): 'info' | 'warn' | 'error' {
  if (level === 'warning') return 'warn'
  if (level === 'error' || level === 'critical') return 'error'
  return 'info'
}

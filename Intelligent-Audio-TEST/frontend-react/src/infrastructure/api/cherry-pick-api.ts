/**
 * 挑选合并 API（infrastructure/api，18_挑选合并交互重设计.md §7.3，INT-713）。
 * 真实接口（经 client.ts 统一信封解包；后端缺口按 §11-2/§11-5 降级，不写兼容层）：
 *   GET    /api/v1/tasks/cherry-picks/candidates      （候选行，多条件 AND）
 *   GET    /api/v1/tasks/cherry-picks/cart            （购物车读）
 *   POST   /api/v1/tasks/cherry-picks/cart/items      （加购）
 *   POST   /api/v1/tasks/cherry-picks/cart/items/remove （移除单条/节点/整组/批量）
 *   DELETE /api/v1/tasks/cherry-picks/cart/items      （清空）
 *   POST   /api/v1/tasks/cherry-picks/cart/save-as-set （另存挑选集）
 *   GET    /api/v1/tasks/cherry-picks/sets            （挑选集列表）
 *   POST   /api/v1/tasks/cherry-picks/sets/{id}/to-cart（恢复挑选集）
 *   DELETE /api/v1/tasks/cherry-picks/sets/{id}       （删除挑选集）
 *   POST   /api/v1/tasks/cherry-picks/preview         （复核摘要）
 *   POST   /api/v1/tasks/cherry-picks/cart/checkout   （下单，action=merge/reexecute/reevaluate）
 * 统一容器列表：GET /api/v1/tasks?merged=true ∪ cherry_pick=true 双查询合并（§11-1）。
 * 名称装饰：candidates/cart 缺 case_name/device_name/api_name（§11-2/§11-5），
 * 本层经真实 test-devices / apis / testcases 列表构建 name map 注入 adapter。
 */
import type { PickNameMaps } from '@/infrastructure/adapters/dto/cherry-pick-adapter'
import {
  fromCandidateDto,
  fromCartGroupDto,
  fromContainerDto,
  fromPreviewDto,
  fromSetListItemDto,
} from '@/infrastructure/adapters/dto/cherry-pick-adapter'
import type {
  CheckoutAction,
  CherryPickCandidate,
  CherryPickContainer,
  PickCartGroup,
  PickPreview,
  PickSet,
} from '@/domain/models/cherryPick'
import { request } from './client'
import { ApiError } from './api-error'
import type {
  CherryPickAddResultDto,
  CherryPickCandidateDto,
  CherryPickCartDto,
  CherryPickMergeResultDto,
  CherryPickPreviewDto,
  CherryPickReevaluateResultDto,
  CherryPickReexecuteResultDto,
  CherryPickRemoveResultDto,
  CherryPickRestoreResultDto,
  CherryPickSaveSetResultDto,
  CherryPickSetListItemDto,
  CherryPickSourceTraceDto,
  TaskContainerItemDto,
  TaskListPageDto,
} from '@/infrastructure/dto/cherry-pick.dto'

/** 候选筛选条件（多条件 AND，§3.4；后端不支持的维度由本层客户端过滤降级） */
export interface CherryPickFilters {
  search?: string
  taskIds?: number[]
  deviceIds?: number[]
  apiIds?: number[]
  resultType?: string[]
  executionStatus?: string[]
  evaluationStatus?: string[]
  timeRange?: string
}

/* ============================================================
 * 名称装饰（真实列表源：test-devices / apis / testcases）
 * 设备/API 名（快，候选/购物车直用）；用例名（testcases 全量分页较慢，
 * 不阻塞候选查询——hook 层背景拉取后对候选行二次装饰）。
 * ============================================================ */

const MAX_OPTION_PAGE = 200

let deviceApiMapsPromise: Promise<{ devices: Map<number, string>; apis: Map<number, string> }> | null =
  null

/** 设备名 map（GET /test-devices 全量；失败降级空 map → 缺名显示设备 ID） */
async function fetchDeviceNameMap(): Promise<Map<number, string>> {
  try {
    const data = await request<TaskListPageDto<{ id: number; name: string }>>(
      'GET',
      '/test-devices',
      undefined,
      { params: { page: 1, per_page: MAX_OPTION_PAGE } }
    )
    return new Map((data.items ?? []).map((d) => [d.id, d.name]))
  } catch {
    return new Map()
  }
}

/** API 名 map（GET /apis 全量） */
async function fetchApiNameMap(): Promise<Map<number, string>> {
  try {
    const data = await request<TaskListPageDto<{ id: number; name: string }>>(
      'GET',
      '/apis',
      undefined,
      { params: { page: 1, per_page: MAX_OPTION_PAGE } }
    )
    return new Map((data.items ?? []).map((d) => [d.id, d.name]))
  } catch {
    return new Map()
  }
}

/** 会话级设备/API 名缓存（快路径：候选与购物车直用，不阻塞） */
export function getDeviceApiNameMaps(): Promise<{
  devices: Map<number, string>
  apis: Map<number, string>
}> {
  if (!deviceApiMapsPromise) {
    deviceApiMapsPromise = (async () => {
      const [devices, apis] = await Promise.all([
        fetchDeviceNameMap(),
        fetchApiNameMap(),
      ])
      return { devices, apis }
    })()
  }
  return deviceApiMapsPromise
}

let caseNameMapPromise: Promise<Map<string, string>> | null = null

/** 用例名 map（GET /testcases 全量分页并行；579 量级，一次会话缓存；
 *  慢路径不阻塞候选——hook 层背景拉取，就绪后对候选行 caseName 二次装饰） */
export function fetchPickCaseNames(): Promise<Map<string, string>> {
  if (!caseNameMapPromise) {
    caseNameMapPromise = (async () => {
      const map = new Map<string, string>()
      try {
        const first = await request<TaskListPageDto<{ id: string; name: string }>>(
          'GET',
          '/testcases',
          undefined,
          { params: { page: 1, per_page: MAX_OPTION_PAGE } }
        )
        for (const c of first.items ?? []) map.set(c.id, c.name)
        const pages = first.pages ?? 1
        if (pages > 1) {
          const rest = await Promise.all(
            Array.from({ length: pages - 1 }, (_, i) =>
              request<TaskListPageDto<{ id: string; name: string }>>(
                'GET',
                '/testcases',
                undefined,
                { params: { page: i + 2, per_page: MAX_OPTION_PAGE } }
              ).catch(() => null)
            )
          )
          for (const data of rest) {
            for (const c of data?.items ?? []) map.set(c.id, c.name)
          }
        }
      } catch {
        // 用例名不可用 → 缺名降级显示用例 ID
      }
      return map
    })()
  }
  return caseNameMapPromise
}

/** 快路径名称 maps（设备/API 已就绪；用例名留空由 hook 二次装饰） */
async function getFastNameMaps(): Promise<PickNameMaps> {
  const { devices, apis } = await getDeviceApiNameMaps()
  return { devices, apis, cases: new Map() }
}

/* ============================================================
 * 时间范围 → start_date/end_date（§3.4 时间筛选，ISO 口径对齐后端）
 * ============================================================ */

function toIsoDaysAgo(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  d.setHours(0, 0, 0, 0)
  return d.toISOString()
}

function timeRangeToDates(
  timeRange: string | undefined
): { startDate?: string; endDate?: string } {
  if (!timeRange || timeRange === 'all') return {}
  const now = new Date()
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const startOfToday = todayStart.toISOString()
  switch (timeRange) {
    case 'today':
      return { startDate: startOfToday }
    case 'yesterday': {
      const yesterdayStart = new Date(todayStart.getTime() - 24 * 3600 * 1000)
      return { startDate: yesterdayStart.toISOString(), endDate: startOfToday }
    }
    case 'week':
      return { startDate: toIsoDaysAgo(7) }
    case 'month':
      return { startDate: toIsoDaysAgo(30) }
    default:
      return {}
  }
}

/* ============================================================
 * 候选查询 / 筛选选项
 * ============================================================ */

/** 候选查询（GET /tasks/cherry-picks/candidates；per_page 封顶 200，§11-3 降级已加载页） */
export async function fetchCherryPickCandidates(
  filters: CherryPickFilters = {}
): Promise<CherryPickCandidate[]> {
  const names = await getFastNameMaps()
  const params: Record<string, unknown> = { page: 1, per_page: MAX_OPTION_PAGE }
  if (filters.taskIds && filters.taskIds.length > 0) {
    params.task_ids = filters.taskIds.join(',')
  }
  if (filters.deviceIds && filters.deviceIds.length > 0) {
    params.device_ids = filters.deviceIds.join(',')
  }
  if (filters.executionStatus && filters.executionStatus.length > 0) {
    params.execution_status = filters.executionStatus[0]
  }
  if (filters.evaluationStatus && filters.evaluationStatus.length > 0) {
    // UI 选项 unevaluated ↔ 后端 EvaluationStatus.PENDING 口径（实测）
    params.evaluation_status =
      filters.evaluationStatus[0] === 'unevaluated' ? 'pending' : 'evaluated'
  }
  const { startDate, endDate } = timeRangeToDates(filters.timeRange)
  if (startDate) params.start_date = startDate
  if (endDate) params.end_date = endDate

  const data = await request<TaskListPageDto<CherryPickCandidateDto>>(
    'GET',
    '/tasks/cherry-picks/candidates',
    undefined,
    { params }
  )
  let items = (data.items ?? []).map((dto) => fromCandidateDto(dto, names))

  // 后端未支持维度 → 客户端过滤（api_ids / result_type；§11-2 候选补字段后落服务端）
  if (filters.apiIds && filters.apiIds.length > 0) {
    const idSet = new Set(filters.apiIds)
    items = items.filter((c) => c.apiId != null && idSet.has(c.apiId))
  }
  if (filters.resultType && filters.resultType.length > 0) {
    const rtSet = new Set(filters.resultType)
    items = items.filter((c) => c.resultType != null && rtSet.has(c.resultType))
  }
  // search 命中用例名/用例 ID/任务名：用例名依赖慢路径装饰，由 hook 层二次过滤
  return items
}

/** 候选行结果类型去重集合（§11-2 候选未返 result_type → 空选项，facet 显示「无选项」） */
export async function fetchResultTypeOptions(): Promise<string[]> {
  const items = await fetchBaseCandidates()
  return [...new Set(items.map((c) => c.resultType).filter((t): t is string => t != null))]
}

/** 可挑选来源任务集合（候选行聚合去重） */
export async function fetchPickableTasks(): Promise<{ id: number; name: string }[]> {
  const items = await fetchBaseCandidates()
  const map = new Map<number, string>()
  for (const c of items) map.set(c.taskId, c.taskName)
  return [...map].map(([id, name]) => ({ id, name }))
}

/** 设备集合（候选行聚合去重 + 设备表名装饰；§11-2 缺名降级「设备 {id}」） */
export async function fetchPickableDevices(): Promise<{ id: number; name: string }[]> {
  const { devices } = await getDeviceApiNameMaps()
  const items = await fetchBaseCandidates()
  const map = new Map<number, string>()
  for (const c of items) {
    if (c.deviceId != null) {
      map.set(c.deviceId, devices.get(c.deviceId) ?? `设备 ${c.deviceId}`)
    }
  }
  return [...map].map(([id, name]) => ({ id, name }))
}

/** 未筛选候选（筛选选项数据源；30s 会话缓存，避免三处选项各拉一次全量）。
 *  INT-1280：并发在途合并为同一 promise，向导挂载时三处选项不再各发起一条
 *  candidates 慢查询（真实库 10–45s），改为共享一次结果。 */
let baseCandidatesCache: { data: CherryPickCandidate[]; ts: number } | null = null
let baseCandidatesPromise: Promise<CherryPickCandidate[]> | null = null

async function fetchBaseCandidates(): Promise<CherryPickCandidate[]> {
  if (baseCandidatesCache && Date.now() - baseCandidatesCache.ts < 30_000) {
    return baseCandidatesCache.data
  }
  if (!baseCandidatesPromise) {
    baseCandidatesPromise = fetchCherryPickCandidates({})
      .then((items) => {
        baseCandidatesCache = { data: items, ts: Date.now() }
        return items
      })
      .finally(() => {
        baseCandidatesPromise = null
      })
  }
  return baseCandidatesPromise
}

/** 测试用：重置会话缓存（vitest / 走查隔离） */
export function __resetCherryPickSessionCache() {
  deviceApiMapsPromise = null
  caseNameMapPromise = null
  baseCandidatesCache = null
}

/* ============================================================
 * 购物车
 * ============================================================ */

/** 购物车读（GET /tasks/cherry-picks/cart，per-user 分组返回；用例名留空由调用方二次装饰） */
export async function fetchCart(): Promise<PickCartGroup[]> {
  const names = await getFastNameMaps()
  const data = await request<CherryPickCartDto>('GET', '/tasks/cherry-picks/cart')
  return (data.groups ?? []).map((g) => fromCartGroupDto(g, names))
}

/** 加购（POST /tasks/cherry-picks/cart/items {result_ids}；重复幂等跳过 uq_cherry_cart_user_result） */
export async function addToCart(resultIds: number[]): Promise<{
  addedCount: number
  skippedCount: number
  invalidCount: number
}> {
  const data = await request<CherryPickAddResultDto>(
    'POST',
    '/tasks/cherry-picks/cart/items',
    { result_ids: resultIds }
  )
  return {
    addedCount: (data.added ?? []).length,
    skippedCount: (data.duplicated ?? []).length,
    invalidCount: (data.missing ?? []).length,
  }
}

/** 移除（POST /tasks/cherry-picks/cart/items/remove {item_ids}；单条/节点/整组/批量） */
export async function removeCartItems(itemIds: string[]): Promise<{ removed: number }> {
  const data = await request<CherryPickRemoveResultDto>(
    'POST',
    '/tasks/cherry-picks/cart/items/remove',
    { item_ids: itemIds.map(Number) }
  )
  return { removed: data.removed }
}

/** 清空购物车（DELETE /tasks/cherry-picks/cart/items） */
export async function clearCart(): Promise<{ cleared: number }> {
  const data = await request<CherryPickRemoveResultDto>(
    'DELETE',
    '/tasks/cherry-picks/cart/items'
  )
  return { cleared: data.removed }
}

/* ============================================================
 * 挑选集
 * ============================================================ */

/** 挑选集列表（GET /tasks/cherry-picks/sets） */
export async function fetchPickSets(): Promise<PickSet[]> {
  const data = await request<{ items: CherryPickSetListItemDto[] }>(
    'GET',
    '/tasks/cherry-picks/sets'
  )
  return (data.items ?? []).map(fromSetListItemDto)
}

/** 另存挑选集（POST /tasks/cherry-picks/cart/save-as-set {name}；条目快照后端提取） */
export async function savePickSet(name: string): Promise<PickSet> {
  const data = await request<CherryPickSaveSetResultDto>(
    'POST',
    '/tasks/cherry-picks/cart/save-as-set',
    { name }
  )
  return {
    setId: String(data.set_id),
    name: data.name,
    createdAt: null,
    itemCount: data.item_count,
    entries: [],
  }
}

/** 恢复挑选集进购物车（POST /tasks/cherry-picks/sets/{id}/to-cart） */
export async function restorePickSet(setId: string): Promise<{ restored: number }> {
  const data = await request<CherryPickRestoreResultDto>(
    'POST',
    `/tasks/cherry-picks/sets/${Number(setId)}/to-cart`
  )
  return { restored: (data.added ?? []).length }
}

/** 删除挑选集（DELETE /tasks/cherry-picks/sets/{id}） */
export async function deletePickSet(setId: string): Promise<void> {
  await request('DELETE', `/tasks/cherry-picks/sets/${Number(setId)}`)
}

/* ============================================================
 * 复核 / 下单
 * ============================================================ */

/** 复核摘要（POST /tasks/cherry-picks/preview；购物车空 → 400 → 兜底空预览） */
export async function fetchCherryPickPreview(): Promise<PickPreview> {
  try {
    const data = await request<CherryPickPreviewDto>(
      'POST',
      '/tasks/cherry-picks/preview'
    )
    return fromPreviewDto(data)
  } catch (err) {
    if (err instanceof ApiError && err.httpStatus === 400) {
      // 购物车为空（后端「购物车为空」400）：返回空预览供复核页空态兜底
      return {
        totalResults: 0,
        invalidResultIds: [],
        sourceTaskCount: 0,
        deviceIds: [],
        caseCount: 0,
        executionStatusCounts: {},
        duplicates: [],
      }
    }
    throw err
  }
}

export interface CheckoutPayload {
  action: CheckoutAction
  name?: string
  description?: string
  algorithm_type?: string
  algorithm_params?: Record<string, unknown>
  config?: Record<string, unknown>
}

export interface CheckoutResult {
  taskId: number
  action: CheckoutAction
  keptItemIds: string[]
}

/** 下单（POST /tasks/cherry-picks/cart/checkout；三出口响应形态按 action 分流） */
export async function checkoutCart(payload: CheckoutPayload): Promise<CheckoutResult> {
  const body: Record<string, unknown> = {
    action: payload.action,
    name: payload.name,
    description: payload.description,
    algorithm_type: payload.algorithm_type,
    algorithm_params: payload.algorithm_params,
    config: payload.config,
  }
  if (payload.action === 'merge') {
    const data = await request<CherryPickMergeResultDto>(
      'POST',
      '/tasks/cherry-picks/cart/checkout',
      body
    )
    return { taskId: data.task_id, action: payload.action, keptItemIds: [] }
  }
  if (payload.action === 'reexecute') {
    const data = await request<CherryPickReexecuteResultDto>(
      'POST',
      '/tasks/cherry-picks/cart/checkout',
      body
    )
    return { taskId: data.task_id, action: payload.action, keptItemIds: [] }
  }
  const data = await request<CherryPickReevaluateResultDto>(
    'POST',
    '/tasks/cherry-picks/cart/checkout',
    body
  )
  return {
    taskId: (data.submitted_task_ids ?? [])[0] ?? 0,
    action: payload.action,
    keptItemIds: [],
  }
}

/* ============================================================
 * 统一容器列表（§11-1 落地前客户端双查询合并）
 * ============================================================ */

export interface ContainerFilters {
  search?: string
  mergeType?: 'whole' | 'picked' | 'all'
}

/** 统一合并容器列表（GET /tasks?merged=true ∪ GET /tasks?cherry_pick=true 双查询合并；
 *  picked 容器 source_tasks 后端 read model 未填 → 溯源端点逐容器补全） */
export async function fetchCherryPickContainers(
  filters: ContainerFilters = {}
): Promise<{ items: CherryPickContainer[]; total: number }> {
  const baseParams: Record<string, unknown> = { page: 1, per_page: MAX_OPTION_PAGE }
  if (filters.search && filters.search.trim()) baseParams.search = filters.search.trim()

  const [wholeRes, pickedRes] = await Promise.all([
    request<TaskListPageDto<TaskContainerItemDto>>('GET', '/tasks', undefined, {
      params: { ...baseParams, merged: true },
    }),
    request<TaskListPageDto<TaskContainerItemDto>>('GET', '/tasks', undefined, {
      params: { ...baseParams, cherry_pick: true },
    }),
  ])

  const wholeItems = (wholeRes.items ?? []).map((it) =>
    fromContainerDto({ ...it, mergeType: 'whole' })
  )
  const pickedItems = (pickedRes.items ?? []).map((it) =>
    fromContainerDto({ ...it, mergeType: 'picked' })
  )
  // 溯源补全（仅 picked；接口失败保留空来源，不阻断列表）
  const traced = await Promise.all(
    pickedItems.map(async (container) => {
      try {
        const trace = await request<CherryPickSourceTraceDto>(
          'GET',
          `/tasks/cherry-picks/${container.id}/source`
        )
        const sourceResults = (trace.groups ?? []).map((g) => ({
          source_task_id: g.source_task_id,
          source_task_name: g.source_task_name,
          count: (g.results ?? []).length,
        }))
        const raw = (pickedRes.items ?? []).find((it) => it.id === container.id)
        if (raw) return fromContainerDto({ ...raw, mergeType: 'picked' }, sourceResults)
        return container
      } catch {
        return container
      }
    })
  )

  let items = [...wholeItems, ...traced].sort((a, b) =>
    (b.createdAt ?? '').localeCompare(a.createdAt ?? '')
  )
  if (filters.mergeType && filters.mergeType !== 'all') {
    items = items.filter((c) => c.mergeType === filters.mergeType)
  }
  return { items, total: items.length }
}

/**
 * 挑选合并 API（infrastructure/api，18_挑选合并交互重设计.md §7.3，INT-713）。
 * 真实接口（经 client.ts 统一信封解包；后端缺口按 §11-2/§11-5 降级，不写兼容层）：
 *   GET    /api/v1/tasks/cherry-picks/pickable-tasks （阶段 1 可挑选任务清单，INT-1496）
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
  fromPickableTaskDto,
  fromPreviewDto,
  fromSetListItemDto,
  fromSourceTraceDto,
} from '@/infrastructure/adapters/dto/cherry-pick-adapter'
import type {
  CheckoutAction,
  CherryPickCandidate,
  CherryPickContainer,
  ContainerSourceTrace,
  PickableTask,
  PickableTaskPage,
  PickableTaskSortBy,
  PickableTaskSortOrder,
  PickableTaskStatus,
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
  PickableTaskPageDto,
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

/* ============================================================
 * 可挑选任务清单（阶段 1 数据源，INT-1496 §8.1）
 * 服务端任务级聚合 + 服务端分页/排序；不再由 candidates 首页 200 行客户端聚合。
 * ============================================================ */

/** 可挑选任务查询（服务端参数；`status` 是**任务**状态，非结果级） */
export interface PickableTaskFilters {
  /** 任务名模糊匹配（后端只匹配任务名，不匹配任务 ID） */
  keyword?: string
  /** 任务状态过滤（completed/failed/stopped；缺省 = 全部三终态） */
  status?: PickableTaskStatus
  /** 排序键，缺省 status（权重 completed→failed→stopped，同权重按任务名） */
  sortBy?: PickableTaskSortBy
  sortOrder?: PickableTaskSortOrder
}

export interface PickableTaskQuery extends PickableTaskFilters {
  page?: number
  perPage?: number
}

/** 单页可挑选任务（GET /tasks/cherry-picks/pickable-tasks；per_page 上限 200） */
export async function fetchPickableTaskPage(
  query: PickableTaskQuery = {}
): Promise<PickableTaskPage> {
  const params: Record<string, unknown> = {
    page: query.page ?? 1,
    per_page: query.perPage ?? MAX_OPTION_PAGE,
  }
  if (query.keyword && query.keyword.trim()) params.keyword = query.keyword.trim()
  if (query.status) params.status = query.status
  if (query.sortBy) params.sort_by = query.sortBy
  if (query.sortOrder) params.sort_order = query.sortOrder

  const data = await request<PickableTaskPageDto>(
    'GET',
    '/tasks/cherry-picks/pickable-tasks',
    undefined,
    { params }
  )
  return {
    items: (data.items ?? []).map(fromPickableTaskDto),
    total: data.total ?? 0,
    page: data.page ?? params.page,
    perPage: data.per_page ?? params.per_page,
  }
}

/** 按 per_page 拉齐分页（阶段 1 清单与「全选当前筛选」须覆盖 total 全部任务，
 *  不允许只取首页）；`MAX_FULL_PAGES` 防御异常 total 造成的长循环。 */
const MAX_FULL_PAGES = 10

export async function fetchAllPickableTasks(
  filters: PickableTaskFilters = {}
): Promise<{ items: PickableTask[]; total: number }> {
  const first = await fetchPickableTaskPage({
    ...filters,
    page: 1,
    perPage: MAX_OPTION_PAGE,
  })
  const items = [...first.items]
  const pages = Math.min(
    Math.ceil(first.total / MAX_OPTION_PAGE),
    MAX_FULL_PAGES
  )
  if (pages > 1) {
    const rest = await Promise.all(
      Array.from({ length: pages - 1 }, (_, i) =>
        fetchPickableTaskPage({
          ...filters,
          page: i + 2,
          perPage: MAX_OPTION_PAGE,
        }).catch(() => null)
      )
    )
    for (const data of rest) {
      if (data) items.push(...data.items)
    }
  }
  return { items, total: first.total }
}

/** 「来源任务」筛选选项（同源 pickable-tasks 全量；与阶段 1 清单同一数据源） */
export async function fetchPickableTaskOptions(): Promise<{ id: number; name: string }[]> {
  const { items } = await fetchAllPickableTasks({ sortBy: 'name', sortOrder: 'asc' })
  return items.map((t) => ({ id: t.taskId, name: t.taskName }))
}

/* ============================================================
 * 阶段 2 候选 facet（设备 / 结果类型，仍由 candidates 首页 200 行重建，§11-3 降级不在本卡范围）
 * ============================================================ */

/** 阶段 2 facet 数据源（一次 candidates 查询同时出设备/结果类型选项；会话内由
 *  React Query 缓存与并发去重，不再保留模块级 30s 兜底缓存——阶段 1 已不经过 candidates） */
export async function fetchCandidateFacets(): Promise<{
  devices: { id: number; name: string }[]
  resultTypes: string[]
}> {
  const { devices } = await getDeviceApiNameMaps()
  const items = await fetchCherryPickCandidates({})
  return {
    devices: buildDeviceFacet(items, devices),
    resultTypes: [...new Set(items.map((c) => c.resultType).filter((t): t is string => t != null))],
  }
}

/** 设备集合（候选行聚合去重 + 设备表名装饰；§11-2 缺名降级「设备 {id}」） */
function buildDeviceFacet(
  items: CherryPickCandidate[],
  devices: Map<number, string>
): { id: number; name: string }[] {
  const map = new Map<number, string>()
  for (const c of items) {
    if (c.deviceId != null) {
      map.set(c.deviceId, devices.get(c.deviceId) ?? `设备 ${c.deviceId}`)
    }
  }
  return [...map].map(([id, name]) => ({ id, name }))
}

/** 测试用：重置会话缓存（vitest / 走查隔离） */
export function __resetCherryPickSessionCache() {
  deviceApiMapsPromise = null
  caseNameMapPromise = null
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
 * 容器溯源 + 统一容器列表（§11-1 落地前客户端双查询合并）
 * ============================================================ */

/**
 * 容器溯源（GET /tasks/cherry-picks/{taskId}/source，§5.5.2 ⑤）：
 * 200 且 groups 非空 → 挑选合并容器；200 且 groups=[] → 容器（关系行缺失）；
 * **任意 `ApiError`（非容器实测 HTTP 400 / `code:203`，以及 5xx / 网络中断）→ null**，
 * 由详情页按「非挑选合并容器」静默处理，绝不因这个可选增强区把详情页变错误态。
 */
export async function fetchContainerSourceTrace(
  taskId: number
): Promise<ContainerSourceTrace | null> {
  try {
    const dto = await request<CherryPickSourceTraceDto>(
      'GET',
      `/tasks/cherry-picks/${Number(taskId)}/source`
    )
    return fromSourceTraceDto(dto)
  } catch (err) {
    if (err instanceof ApiError) return null
    throw err
  }
}

export interface ContainerFilters {
  search?: string
  mergeType?: 'whole' | 'picked' | 'all'
}

/**
 * 容器溯源（GET /tasks/cherry-picks/{task_id}/source，§8 S3）。
 * 挑选合并容器的每条引用结果都带回来源任务（source_task_id）——复核留痕按
 * 结果归属任务落库，容器详情查复核计数/历史须按来源任务查（INT-1626）。
 * 非容器任务后端返 success=false/code=404，本层归一 null，调用侧回落到页面 taskId；
 * 其余错误同样降级为 null，不因溯源查询失败阻断任务详情。
 */
export async function fetchContainerSourceTrace(
  taskId: number
): Promise<CherryPickSourceTraceDto | null> {
  try {
    return await request<CherryPickSourceTraceDto>(
      'GET',
      `/tasks/cherry-picks/${Number(taskId)}/source`
    )
  } catch (err) {
    if (err instanceof ApiError) return null
    throw err
  }
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

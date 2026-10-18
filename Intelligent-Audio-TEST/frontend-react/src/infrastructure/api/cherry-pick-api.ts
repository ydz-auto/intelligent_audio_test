/**
 * 挑选合并 API（infrastructure/api 层，接线基座 INT-605 client.ts 出口；
 * 18_挑选合并交互重设计.md §7.3，INT-339 §8 契约，INT-623 Vue 侧已比对后端契约）。
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
 * 统一容器列表：GET /api/v1/tasks?merged=true ∪ cherry_pick=true（§11-1 客户端双查询合并）
 */
import type {
  CheckoutAction,
  CherryPickCandidate,
  CherryPickContainer,
  PickCartGroup,
  PickPreview,
  PickSet,
} from '@/domain/models/cherryPick'
import {
  fromCandidateDto,
  fromCartEntryDto,
  fromContainerDto,
  fromPickSetDto,
  fromPreviewDto,
} from '@/infrastructure/adapters/dto/cherry-pick-adapter'
import { request } from '@/infrastructure/api/client'
import type {
  CheckoutResultDto,
  CherryPickCandidatePageDto,
  PickCartDto,
  PickPreviewDto,
  PickSetDto,
} from '@/infrastructure/dto/cherry-pick.dto'
import type { PaginatedDto, TaskListItemDto } from '@/infrastructure/dto/task.dto'

/** 候选筛选条件（多条件 AND，§3.4；后端支持 task_ids/device_ids/case_keyword/
 *  execution_status/evaluation_status/start_date/end_date） */
export interface CherryPickFilters {
  search?: string
  taskIds?: number[]
  deviceIds?: number[]
  /** 后端候选查询未支持（无 api_ids 参数，§3.4 点名维度缺口 → FEAT 证据见 INT-638） */
  apiIds?: number[]
  /** 后端候选行未返 result_type → 筛选器选项缺省（FEAT 证据见 INT-638） */
  resultType?: string[]
  /** 后端仅接受单值 execution_status；多选时仅透传首项（多值缺口 FEAT 证据） */
  executionStatus?: string[]
  /** 后端语义为 evaluated/pending 二态；completed/evaluating/failed/skipped → evaluated */
  evaluationStatus?: string[]
  /** 时间范围后端按 start_date/end_date ISO 透传；timeRange 快捷值映射见调用方 */
  timeRange?: string
}

const OPTIONS_PAGE_SIZE = 200

/** 候选查询（真实接口 AND 组合；缺名字段前端按 ID/缺省降级，§11-2） */
export async function fetchCherryPickCandidates(
  filters: CherryPickFilters = {}
): Promise<CherryPickCandidate[]> {
  const params: Record<string, unknown> = { page: 1, per_page: OPTIONS_PAGE_SIZE }
  // 前端 search 命中用例名/用例ID → 后端 case_keyword（INT-401 语义）
  if (filters.search) params.case_keyword = filters.search
  // 逗号分隔多值（GET 查询串契约，cherry_pick_service._split_ints）
  if (filters.taskIds && filters.taskIds.length > 0) {
    params.task_ids = filters.taskIds.join(',')
  }
  if (filters.deviceIds && filters.deviceIds.length > 0) {
    params.device_ids = filters.deviceIds.join(',')
  }
  if (filters.executionStatus && filters.executionStatus.length > 0) {
    // 后端仅单值；多选暂取首项（多值筛选缺口 → FEAT 证据）
    params.execution_status = filters.executionStatus[0]
  }
  if (filters.evaluationStatus && filters.evaluationStatus.length > 0) {
    // 后端 evaluation_status 二态（evaluated/pending）；已评估族收敛为 evaluated
    params.evaluation_status = filters.evaluationStatus.includes('pending')
      ? 'pending'
      : 'evaluated'
  }
  // apiIds/resultType/timeRange：后端候选查询未支持，未透传（FEAT 证据见 INT-638）

  const dto = await request<CherryPickCandidatePageDto>(
    'GET',
    '/tasks/cherry-picks/candidates',
    undefined,
    { params }
  )
  return (dto.items ?? []).map(fromCandidateDto)
}

/** 候选行结果类型去重集合（后端候选行未返 result_type → 缺省 'default'，§11-2 降级） */
export async function fetchResultTypeOptions(): Promise<string[]> {
  const candidates = await fetchCherryPickCandidates()
  const types = new Set(candidates.map((c) => c.resultType))
  return [...types]
}

/** 可挑选来源任务集合（候选行聚合去重，§3.4 来源任务筛选选项） */
export async function fetchPickableTasks(): Promise<{ id: number; name: string }[]> {
  const candidates = await fetchCherryPickCandidates()
  const map = new Map<number, string>()
  for (const c of candidates) map.set(c.taskId, c.taskName)
  return [...map].map(([id, name]) => ({ id, name }))
}

/** 设备集合（候选行 device_id 聚合；后端候选行未返 device_name → 显示「设备 {id}」） */
export async function fetchPickableDevices(): Promise<{ id: number; name: string }[]> {
  const candidates = await fetchCherryPickCandidates()
  const map = new Map<number, string>()
  for (const c of candidates) {
    if (c.deviceId != null) map.set(c.deviceId, `设备 ${c.deviceId}`)
  }
  return [...map].map(([id, name]) => ({ id, name }))
}

// ============================================================
// 购物车（per-user；服务端为准，本地为镜像）
// ============================================================

/** 购物车读（按来源任务分组返回，per-user 实测） */
export async function fetchCart(): Promise<PickCartGroup[]> {
  const dto = await request<PickCartDto>('GET', '/tasks/cherry-picks/cart')
  return (dto.groups ?? []).map((g) => ({
    taskId: g.source_task_id,
    taskName: g.source_task_name,
    entries: (g.items ?? []).map(fromCartEntryDto),
  }))
}

/** 加购（按 result_id 建立条目快照；重复加购幂等跳过 uq_cherry_cart_user_result） */
export async function addToCart(resultIds: number[]): Promise<{
  addedCount: number
  skippedCount: number
  invalidCount: number
}> {
  // 后端返回 { added: int[], missing: int[], duplicated: int[] }（result_id 集，非条目快照）；
  // 购物车镜像随后以 refreshCart 服务端全量回写为准
  const dto = await request<{ added?: number[]; duplicated?: number[]; missing?: number[] }>(
    'POST',
    '/tasks/cherry-picks/cart/items',
    { result_ids: resultIds }
  )
  return {
    addedCount: dto.added?.length ?? resultIds.length,
    skippedCount: dto.duplicated?.length ?? 0,
    invalidCount: dto.missing?.length ?? 0,
  }
}

/** 移除（item_ids 数组：单条/节点/整组/批量/失效全矩阵，§4.3；后端条目 ID 为整型） */
export async function removeCartItems(itemIds: string[]): Promise<{ removed: number }> {
  return request<{ removed: number }>(
    'POST',
    '/tasks/cherry-picks/cart/items/remove',
    { item_ids: itemIds.map(Number) }
  )
}

/** 清空购物车 */
export async function clearCart(): Promise<{ cleared: number }> {
  return request<{ cleared: number }>('DELETE', '/tasks/cherry-picks/cart/items')
}

// ============================================================
// 挑选集
// ============================================================

/** 挑选集列表（后端 sets_list 返回摘要：set_id/name/item_count/created_at；不含条目） */
export async function fetchPickSets(): Promise<PickSet[]> {
  const dto = await request<{ items: PickSetDto[] }>('GET', '/tasks/cherry-picks/sets')
  return (dto.items ?? []).map(fromPickSetDto)
}

/** 另存挑选集（后端返回 { set_id, name, item_count }） */
export async function savePickSet(name: string): Promise<PickSet> {
  const dto = await request<PickSetDto>('POST', '/tasks/cherry-picks/cart/save-as-set', {
    name,
  })
  return fromPickSetDto(dto)
}

/** 恢复挑选集进购物车（后端返回 { added, missing, duplicated } result_id 集） */
export async function restorePickSet(setId: string): Promise<{ restored: number }> {
  const dto = await request<{ added?: number[] }>(
    'POST',
    `/tasks/cherry-picks/sets/${Number(setId)}/to-cart`
  )
  return { restored: dto.added?.length ?? 0 }
}

/** 删除挑选集（后端 set_id 整型；删除后由 refreshPickSets 回写） */
export async function deletePickSet(setId: string): Promise<void> {
  await request<{ deleted: number }>(
    'DELETE',
    `/tasks/cherry-picks/sets/${Number(setId)}`
  )
}

// ============================================================
// 复核 / 下单
// ============================================================

/** 复核摘要（POST /tasks/cherry-picks/preview 零新增接口） */
export async function fetchCherryPickPreview(): Promise<PickPreview> {
  const dto = await request<PickPreviewDto>('POST', '/tasks/cherry-picks/preview')
  return fromPreviewDto(dto)
}

export interface CheckoutPayload {
  action: CheckoutAction
  name?: string
  description?: string
  /** 任务级配置覆盖（§5.2；algorithm_type 等字段拆分透传后端） */
  config?: Record<string, unknown>
}

export interface CheckoutResult {
  taskId: number | null
  action: CheckoutAction
  /** 出清后保留条目（失效/重复）；后端内部出清，响应未返 → 恒空，由 refreshCart 回写 */
  keptItemIds: string[]
}

/** 下单（三出口 merge/reexecute/reevaluate；出清由后端处理） */
export async function checkoutCart(payload: CheckoutPayload): Promise<CheckoutResult> {
  const body: Record<string, unknown> = { action: payload.action }
  if (payload.name) body.name = payload.name
  if (payload.description) body.description = payload.description
  // §5.2 任务级配置覆盖：config 对象内 algorithm_type/algorithm_params 拆分透传
  if (payload.config) {
    if (typeof payload.config.algorithm_type === 'string') {
      body.algorithm_type = payload.config.algorithm_type
    }
    if (payload.config.algorithm_params) {
      body.algorithm_params = payload.config.algorithm_params
    }
    body.config = payload.config
  }
  const dto = await request<CheckoutResultDto>(
    'POST',
    '/tasks/cherry-picks/cart/checkout',
    body
  )
  return {
    taskId: dto.task_id ?? null,
    action: payload.action,
    keptItemIds: [],
  }
}

// ============================================================
// 统一容器列表（§11-1 落地前客户端双查询合并：merged=true ∪ cherry_pick=true）
// ============================================================

export interface ContainerFilters {
  search?: string
  mergeType?: 'whole' | 'picked' | 'all'
}

/** 统一合并容器列表（双 query 合并：整任务合并 merged=true ∪ 结果挑选 cherry_pick=true） */
export async function fetchCherryPickContainers(
  filters: ContainerFilters = {}
): Promise<{ items: CherryPickContainer[]; total: number }> {
  const mergeType = filters.mergeType ?? 'all'
  const queries: Array<Promise<PaginatedDto<TaskListItemDto>>> = []
  if (mergeType === 'whole' || mergeType === 'all') {
    queries.push(
      request<PaginatedDto<TaskListItemDto>>('GET', '/tasks', undefined, {
        params: { page: 1, per_page: 100, merged: true },
      })
    )
  }
  if (mergeType === 'picked' || mergeType === 'all') {
    queries.push(
      request<PaginatedDto<TaskListItemDto>>('GET', '/tasks', undefined, {
        params: { page: 1, per_page: 100, cherry_pick: true },
      })
    )
  }
  const results = await Promise.all(queries)
  const seen = new Set<number>()
  const items: CherryPickContainer[] = []
  for (const page of results) {
    for (const row of page.items ?? []) {
      if (seen.has(row.id)) continue
      seen.add(row.id)
      const container = fromContainerDto(row)
      if (mergeType !== 'all' && container.mergeType !== mergeType) continue
      if (filters.search) {
        const kw = filters.search.trim().toLowerCase()
        if (
          !container.name.toLowerCase().includes(kw) &&
          !(container.description ?? '').toLowerCase().includes(kw)
        ) {
          continue
        }
      }
      items.push(container)
    }
  }
  items.sort((a, b) => (b.createdAt < a.createdAt ? -1 : 1))
  return { items, total: items.length }
}

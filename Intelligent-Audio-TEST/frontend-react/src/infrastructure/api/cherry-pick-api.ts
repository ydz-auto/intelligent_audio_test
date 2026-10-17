/**
 * 挑选合并 API 桩（infrastructure/api，18_挑选合并交互重设计.md §7.3，INT-600）。
 * 全部 mock 常量（红线④），接线后替换为真实请求：
 *   GET    /api/v1/tasks/cherry-picks/candidates      （候选行，§3.4 多条件 AND）
 *   GET    /api/v1/tasks/cherry-picks/cart            （购物车读）
 *   POST   /api/v1/tasks/cherry-picks/cart/items      （加购）
 *   POST   /api/v1/tasks/cherry-picks/cart/items/remove （移除单条/节点/整组/批量）
 *   DELETE /api/v1/tasks/cherry-picks/cart/items      （清空）
 *   POST   /api/v1/tasks/cherry-picks/cart/save-as-set （另存挑选集）
 *   GET    /api/v1/tasks/cherry-picks/sets            （挑选集列表）
 *   POST   /api/v1/tasks/cherry-picks/sets/{id}/to-cart（恢复挑选集）
 *   DELETE /api/v1/tasks/cherry-picks/sets/{id}       （删除挑选集）
 *   POST   /api/v1/tasks/cherry-picks/cart/preview    （复核摘要，零新增接口）
 *   POST   /api/v1/tasks/cherry-picks/cart/checkout   （下单，action=merge/reexecute/reevaluate）
 * 统一容器列表：GET /api/v1/tasks?merged=true ∪ cherry_pick=true（§11-1 落地前客户端双查询合并）
 */
import type {
  CheckoutAction,
  CherryPickCandidate,
  CherryPickContainer,
  PickCartEntry,
  PickCartGroup,
  PickPreview,
  PickSet,
} from '@/domain/models/cherryPick'
import {
  fromCandidateDto,
  fromCartEntryDto,
  fromContainerDto,
  fromPickSetDto,
} from '@/infrastructure/adapters/dto/cherry-pick-adapter'
import {
  MOCK_CANDIDATE_DTOS,
  MOCK_CART_ENTRY_DTOS,
  MOCK_CONTAINER_DTOS,
  MOCK_PICK_SET_DTOS,
} from '@/infrastructure/mock/cherry-pick-mock'

/** 模拟网络延迟（视觉稿演示用；接线后删除） */
function mockLatency<T>(value: T, ms = 120): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

/** 候选筛选条件（多条件 AND，§3.4） */
export interface CherryPickFilters {
  search?: string
  taskIds?: number[]
  deviceIds?: number[]
  apiIds?: number[]
  resultType?: string[]
  executionStatus?: string[]
  evaluationStatus?: string[]
  timeRange?: string
  /** 会话记忆（§6.4：会话级、不持久化） */
}

const ALL_CANDIDATES: CherryPickCandidate[] = MOCK_CANDIDATE_DTOS.map(fromCandidateDto)

/** 候选查询（mock 内存过滤；真实接口 AND 组合，§11-2 补展示字段前缺名降级 ID） */
export async function fetchCherryPickCandidates(
  filters: CherryPickFilters = {}
): Promise<CherryPickCandidate[]> {
  // TODO(API 接线): GET /api/v1/tasks/cherry-picks/candidates?task_ids=&device_ids=…
  let items = ALL_CANDIDATES

  if (filters.search) {
    const kw = filters.search.trim().toLowerCase()
    items = items.filter(
      (c) =>
        (c.caseName ?? '').toLowerCase().includes(kw) ||
        c.caseId.toLowerCase().includes(kw)
    )
  }
  if (filters.taskIds && filters.taskIds.length > 0) {
    items = items.filter((c) => filters.taskIds!.includes(c.taskId))
  }
  if (filters.deviceIds && filters.deviceIds.length > 0) {
    items = items.filter((c) => c.deviceId != null && filters.deviceIds!.includes(c.deviceId))
  }
  if (filters.apiIds && filters.apiIds.length > 0) {
    items = items.filter((c) => c.apiId != null && filters.apiIds!.includes(c.apiId))
  }
  if (filters.resultType && filters.resultType.length > 0) {
    items = items.filter((c) => filters.resultType!.includes(c.resultType))
  }
  if (filters.executionStatus && filters.executionStatus.length > 0) {
    items = items.filter((c) => filters.executionStatus!.includes(c.executionStatus))
  }
  if (filters.evaluationStatus && filters.evaluationStatus.length > 0) {
    items = items.filter((c) => filters.evaluationStatus!.includes(c.evaluationStatus))
  }
  // §11-1 前置：仅终态任务可挑 + excluded=0（mock 已为终态子集）

  return mockLatency([...items])
}

/** 候选行结果类型去重集合（筛选器动态选项数据源，§3.4） */
export async function fetchResultTypeOptions(): Promise<string[]> {
  const types = new Set(ALL_CANDIDATES.map((c) => c.resultType))
  return mockLatency([...types])
}

/** 可挑选来源任务集合（候选行聚合去重，§3.4 来源任务筛选选项） */
export async function fetchPickableTasks(): Promise<{ id: number; name: string }[]> {
  const map = new Map<number, string>()
  for (const c of ALL_CANDIDATES) map.set(c.taskId, c.taskName)
  return mockLatency([...map].map(([id, name]) => ({ id, name })))
}

/** 设备集合（devicesApi.getAllFlat 同源 mock 子集） */
export async function fetchPickableDevices(): Promise<{ id: number; name: string }[]> {
  const map = new Map<number, string>()
  for (const c of ALL_CANDIDATES) {
    if (c.deviceId != null && c.deviceName) map.set(c.deviceId, c.deviceName)
  }
  return mockLatency([...map].map(([id, name]) => ({ id, name })))
}

/* ============================================================
 * 购物车（mock 模块级状态模拟服务端持久化；接线后替换真实端点）
 * ============================================================ */

/** mock 购物车镜像（模块级单例，模拟 per-user 服务端持久化） */
let mockCartEntries: PickCartEntry[] = MOCK_CART_ENTRY_DTOS.map(fromCartEntryDto)

/** 供测试重置（visual mock 会话内持久） */
export function __resetCartMock() {
  mockCartEntries = MOCK_CART_ENTRY_DTOS.map(fromCartEntryDto)
}

function toGroups(entries: PickCartEntry[]): PickCartGroup[] {
  const map = new Map<number, PickCartGroup>()
  for (const e of entries) {
    let g = map.get(e.sourceTaskId)
    if (!g) {
      g = { taskId: e.sourceTaskId, taskName: e.sourceTaskName, entries: [] }
      map.set(e.sourceTaskId, g)
    }
    g.entries.push(e)
  }
  return [...map.values()]
}

/** 购物车读（按来源任务分组返回，per-user 实测） */
export async function fetchCart(): Promise<PickCartGroup[]> {
  // TODO(API 接线): GET /api/v1/tasks/cherry-picks/cart
  return mockLatency(toGroups(mockCartEntries))
}

/** 加购（按 result_id 建立条目快照；重复加购幂等跳过 uq_cherry_cart_user_result） */
export async function addToCart(resultIds: number[]): Promise<{
  added: PickCartEntry[]
  skippedCount: number
  invalidCount: number
}> {
  // TODO(API 接线): POST /api/v1/tasks/cherry-picks/cart/items {result_ids}
  const existingResultIds = new Set(mockCartEntries.map((e) => e.resultId))
  const added: PickCartEntry[] = []
  let skippedCount = 0

  for (const resultId of resultIds) {
    if (existingResultIds.has(resultId)) {
      skippedCount += 1
      continue
    }
    const candidate = ALL_CANDIDATES.find((c) => c.resultId === resultId)
    if (!candidate) continue
    const entry: PickCartEntry = {
      itemId: `ci-${Date.now()}-${resultId}`,
      resultId,
      sourceTaskId: candidate.taskId,
      sourceTaskName: candidate.taskName,
      sourceCaseId: candidate.caseId,
      sourceCaseName: candidate.caseName,
      sourceDeviceId: candidate.deviceId,
      sourceDeviceName: candidate.deviceName,
      sourceApiId: candidate.apiId,
      sourceApiName: candidate.apiName,
      sourceResultType: null, // §11-5 未落前不返
      executionStatus: candidate.executionStatus,
      evaluationStatus: candidate.evaluationStatus,
      invalid: false,
    }
    mockCartEntries = [...mockCartEntries, entry]
    existingResultIds.add(resultId)
    added.push(entry)
  }

  return mockLatency({ added, skippedCount, invalidCount: 0 })
}

/** 移除（item_ids 数组：单条/节点/整组/批量/失效全矩阵，§4.3） */
export async function removeCartItems(itemIds: string[]): Promise<{ removed: number }> {
  // TODO(API 接线): POST /api/v1/tasks/cherry-picks/cart/items/remove {item_ids}
  const idSet = new Set(itemIds)
  const before = mockCartEntries.length
  mockCartEntries = mockCartEntries.filter((e) => !idSet.has(e.itemId))
  return mockLatency({ removed: before - mockCartEntries.length })
}

/** 清空购物车 */
export async function clearCart(): Promise<{ cleared: number }> {
  // TODO(API 接线): DELETE /api/v1/tasks/cherry-picks/cart/items
  const cleared = mockCartEntries.length
  mockCartEntries = []
  return mockLatency({ cleared })
}

/* ============================================================
 * 挑选集
 * ============================================================ */

let mockPickSets: PickSet[] = MOCK_PICK_SET_DTOS.map(fromPickSetDto)

export async function fetchPickSets(): Promise<PickSet[]> {
  // TODO(API 接线): GET /api/v1/tasks/cherry-picks/sets
  return mockLatency([...mockPickSets])
}

export async function savePickSet(name: string): Promise<PickSet> {
  // TODO(API 接线): POST /api/v1/tasks/cherry-picks/cart/save-as-set {name}
  const set: PickSet = {
    setId: `set-${Date.now()}`,
    name,
    createdAt: new Date().toISOString(),
    itemCount: mockCartEntries.length,
    entries: [...mockCartEntries],
  }
  mockPickSets = [...mockPickSets, set]
  return mockLatency(set)
}

export async function restorePickSet(setId: string): Promise<{ restored: number }> {
  // TODO(API 接线): POST /api/v1/tasks/cherry-picks/sets/{id}/to-cart
  const pick = mockPickSets.find((s) => s.setId === setId)
  if (!pick) return mockLatency({ restored: 0 })
  const existing = new Set(mockCartEntries.map((e) => e.resultId))
  const restored = pick.entries.filter((e) => !existing.has(e.resultId))
  mockCartEntries = [...mockCartEntries, ...restored]
  return mockLatency({ restored: restored.length })
}

export async function deletePickSet(setId: string): Promise<void> {
  // TODO(API 接线): DELETE /api/v1/tasks/cherry-picks/sets/{id}
  mockPickSets = mockPickSets.filter((s) => s.setId !== setId)
  return mockLatency(undefined, 60)
}

/* ============================================================
 * 复核 / 下单
 * ============================================================ */

/** 复核摘要（购物车条目派生；真实接口 POST /cart/preview 零新增） */
export async function fetchCherryPickPreview(): Promise<PickPreview> {
  // TODO(API 接线): POST /api/v1/tasks/cherry-picks/cart/preview
  const groups = toGroups(mockCartEntries)
  const total = mockCartEntries.length
  const invalid = mockCartEntries.filter((e) => e.invalid)
  const deviceIds = new Set<number>()
  let caseCount = 0
  const statusCounts: Record<string, number> = {}
  const caseKeys = new Set<string>()
  for (const e of mockCartEntries) {
    if (e.sourceDeviceId != null) deviceIds.add(e.sourceDeviceId)
    caseKeys.add(`${e.sourceTaskId}:${e.sourceCaseId}`)
    statusCounts[e.executionStatus] = (statusCounts[e.executionStatus] ?? 0) + 1
  }
  caseCount = caseKeys.size
  // 同设备同用例多来源组数（不同任务同 case 名近似演示）
  const sourceByCase = new Map<string, Set<number>>()
  for (const g of groups) {
    for (const e of g.entries) {
      const key = `${e.sourceCaseName ?? e.sourceCaseId}`
      let set = sourceByCase.get(key)
      if (!set) {
        set = new Set()
        sourceByCase.set(key, set)
      }
      set.add(g.taskId)
    }
  }
  const duplicates = [...sourceByCase.values()].filter((s) => s.size > 1).length
  return mockLatency({
    totalResults: total,
    invalidResultIds: invalid.map((e) => e.resultId),
    sourceTaskCount: groups.length,
    deviceIds: [...deviceIds],
    caseCount,
    executionStatusCounts: statusCounts,
    duplicates,
    configInconsistent: groups.length > 1,
    configFields: ['algorithm_type'],
    sourceConfigs: groups.map(() => ({ algorithm_type: 'asr_streaming' })),
  })
}

export interface CheckoutPayload {
  action: CheckoutAction
  name?: string
  description?: string
  config?: Record<string, unknown>
}

export interface CheckoutResult {
  taskId: number
  action: CheckoutAction
  keptItemIds: string[]
}

/** 下单（三出口 merge/reexecute/reevaluate；出清已下单条目，失效/重复保留） */
export async function checkoutCart(
  payload: CheckoutPayload
): Promise<CheckoutResult> {
  // TODO(API 接线): POST /api/v1/tasks/cherry-picks/cart/checkout {action, name, ...}
  const taskId = Math.floor(900 + Math.random() * 90)
  // checkout_merge 的 cart_clear(keep_result_ids) 口径：失效条目保留
  const kept = mockCartEntries.filter((e) => e.invalid)
  mockCartEntries = kept
  return mockLatency({ taskId, action: payload.action, keptItemIds: kept.map((e) => e.itemId) })
}

/* ============================================================
 * 统一容器列表（§11-1 落地前客户端双查询合并）
 * ============================================================ */

let mockContainers: CherryPickContainer[] = MOCK_CONTAINER_DTOS.map(fromContainerDto)

export interface ContainerFilters {
  search?: string
  mergeType?: 'whole' | 'picked' | 'all'
}

/** 统一合并容器列表（整任务合并 ∪ 结果挑选，mock 单源合并；真实接线为双 query 合并） */
export async function fetchCherryPickContainers(
  filters: ContainerFilters = {}
): Promise<{ items: CherryPickContainer[]; total: number }> {
  // TODO(API 接线): GET /api/v1/tasks?merged=true + GET /api/v1/tasks?cherry_pick=true 双查询合并
  let items = mockContainers
  if (filters.search) {
    const kw = filters.search.trim().toLowerCase()
    items = items.filter(
      (c) =>
        c.name.toLowerCase().includes(kw) ||
        (c.description ?? '').toLowerCase().includes(kw)
    )
  }
  if (filters.mergeType && filters.mergeType !== 'all') {
    items = items.filter((c) => c.mergeType === filters.mergeType)
  }
  return mockLatency({ items, total: items.length })
}

/** 添加新容器（下单成功后 mock 刷新页签计数，§6.3 同步点） */
export function __addContainerMock(container: CherryPickContainer) {
  mockContainers = [container, ...mockContainers]
}

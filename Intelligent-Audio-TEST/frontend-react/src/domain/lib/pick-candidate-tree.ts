/**
 * 阶段 2 候选树 → 挑选树 / 三视图树（INT-1510 §8.2 接线；INT-1819 / INT-1892）。
 *
 * 树骨架与节点计数的**唯一来源**是 `GET /tasks/cherry-picks/candidates/tree`：
 * 任务 → 用例 → 设备/API → result_type，每个 result_type 节点带 `result_ids`。
 * 叶明细（结果行）不在树响应里：由「叶的父级」节点携带 `leafFilter`，展开时按
 * 「task_ids + case_ids + device_id 或 api_id + result_type」分页拉 candidates。
 *
 * 展示口径沿用 INT-1694（接线不回退）：
 *   用例视图：用例卡 → 设备/API → result_type → 任务 → 叶（首层组织由 PickCaseOrgList 聚合）
 *   设备视图：设备/API → result_type → 用例层组织 → 用例卡 → 任务 → 叶
 *   结果类型视图：result_type → 设备/API → 用例层组织 → 用例卡 → 任务 → 叶
 * 任务层在最末一级（叶的前一级），整棵树只有 1 个任务时省略；
 * result_type 只有 1 种时该层省略（与「结果类型视图」入口同一判定）。
 *
 * 依赖规则：domain 零依赖。
 */
import type {
  PickApiMeta,
  PickCandidateTree,
  PickCaseMeta,
  PickDeviceMeta,
  PickLeafFilter,
  PickTaskMeta,
  PickTreeBranch,
  PickTreeItem,
  PickTreeTaskNode,
} from '@/domain/models/cherryPick'
import {
  PENDING_RESULT_TYPE_KEY,
  PENDING_RESULT_TYPE_LABEL,
  buildCaseOrgBranches,
  hasResultTypeVariety,
} from '@/domain/lib/cherry-pick-tree'
import type {
  PickCaseOrgDimension,
  PickCaseOrgSubView,
} from '@/domain/models/cherryPick'

/** 服务端唯一缺值桶取值（§8.2.2 / §8.2.7；不得另立第二个缺值取值） */
export const PENDING_RESULT_TYPE_VALUE = 'default'

/** 缺名兜底文案（INT-1824 §8.2.8：接口不拼文案，前端兜底，且不裸显 UUID） */
export const UNKNOWN_CASE_NAME = '未知用例'
export const UNKNOWN_DEVICE_NAME = '未知设备'
export const UNKNOWN_API_NAME = '未知API'

/** 缺值桶判定（'default' / 空串 / null 同归「结果类型待补充」） */
export function isPendingResultType(resultType: string | null | undefined): boolean {
  const value = resultType?.trim()
  return !value || value === PENDING_RESULT_TYPE_VALUE
}

/** result_type 展示文案（缺值桶 → 「结果类型待补充」，层级不隐藏，§3.7.1） */
export function resultTypeLabel(resultType: string | null | undefined): string {
  if (isPendingResultType(resultType)) return PENDING_RESULT_TYPE_LABEL
  return resultType!.trim()
}

/** 分组 key：缺值桶用既有 PENDING key，真实取值原样 */
function resultTypeKey(resultType: string | null | undefined): string {
  return isPendingResultType(resultType) ? PENDING_RESULT_TYPE_KEY : resultType!.trim()
}

/** 叶明细过滤口径里的 result_type 取值（缺值桶统一提 'default'） */
function resultTypeFilterValue(resultType: string | null | undefined): string {
  return isPendingResultType(resultType) ? PENDING_RESULT_TYPE_VALUE : resultType!.trim()
}

/** 用例展示名：用例目录查不到 / 已软删 → 「未知用例」（不裸显 UUID） */
export function displayCaseName(meta: PickCaseMeta | undefined): string {
  const name = meta?.caseName?.trim()
  return name && name !== meta?.caseId ? name : UNKNOWN_CASE_NAME
}

/** 设备展示名：设备已软删（device_name=null）→ 「未知设备」 */
export function displayDeviceName(meta: PickDeviceMeta | undefined): string {
  return meta?.deviceName?.trim() || UNKNOWN_DEVICE_NAME
}

/** API 展示名：缺名 → 「未知API」 */
export function displayApiName(meta: PickApiMeta | undefined): string {
  return meta?.apiName?.trim() || UNKNOWN_API_NAME
}

/** 设备/API 二选一 key（与树节点一致） */
function deviceNodeKey(deviceId: number | null, apiId: number | null): string {
  return deviceId != null ? `device:${deviceId}` : `api:${apiId ?? '?'}`
}

/** meta 索引（去重表 → Map，避免逐节点线性查找） */
interface TreeMetaIndex {
  tasks: Map<number, PickTaskMeta>
  cases: Map<string, PickCaseMeta>
  devices: Map<number, PickDeviceMeta>
  apis: Map<number, PickApiMeta>
  /** 三视图叶明细的作用域任务集（阶段 1 已选任务集） */
  taskIds: number[]
}

function indexMeta(tree: PickCandidateTree): TreeMetaIndex {
  return {
    tasks: new Map(tree.meta.tasks.map((t) => [t.taskId, t])),
    cases: new Map(tree.meta.cases.map((c) => [c.caseId, c])),
    devices: new Map(tree.meta.devices.map((d) => [d.deviceId, d])),
    apis: new Map(tree.meta.apis.map((a) => [a.apiId, a])),
    taskIds: tree.tree.map((t) => t.taskId),
  }
}

/** 叶明细过滤口径（展开节点后调 candidates 分页的唯一入参） */
function makeLeafFilter(
  taskIds: number[],
  caseId: string,
  deviceId: number | null,
  apiId: number | null,
  resultType: string | null
): PickLeafFilter {
  return {
    taskIds,
    caseIds: [caseId],
    deviceId,
    apiId,
    resultType: resultType == null ? null : resultTypeFilterValue(resultType),
  }
}

/**
 * 叶的父级节点判定：携带 `leafFilter` 且树上无子节点 —— 其结果行不在树响应里，
 * 由用户显式展开该节点时按需分页（candidates）。「全部展开」必须跳过这类节点，
 * 否则一次挂载全部叶列表 = 全量并发叶查询（真库 2360 个过滤组合）。
 */
export function isLeafParentBranch(branch: PickTreeBranch): boolean {
  return branch.leafFilter != null && branch.children.length === 0
}

/** 叶明细过滤口径的稳定 key（React Query 查询键；节点身份 = 该组合） */
export function buildLeafFilterKey(filter: PickLeafFilter): string {
  return [
    filter.taskIds.join(','),
    filter.caseIds.join(','),
    filter.deviceId ?? '',
    filter.apiId ?? '',
    filter.resultType ?? '',
  ].join('|')
}

/** 用例级元信息挂到分支（用例卡 tags/分组/时长/轮次/算法徽章数据源） */
function caseBranchMeta(meta: PickCaseMeta | undefined) {
  return {
    algorithmType: meta?.algorithmType ?? null,
    tags: meta?.tags ?? [],
    groupId: meta?.groupId ?? null,
    groupName: meta?.groupName ?? null,
    totalDuration: meta?.duration ?? null,
    rounds: meta?.rounds ?? null,
  }
}

/* ============================================================
 * 候选树 → 统一聚合（(用例, 设备/API, result_type) 三点组 + 每任务分桶）
 * 三视图只是同一份聚合的不同投影，计数/resultIds 全程一致。
 * ============================================================ */

/** 单个任务在某个（用例/设备/result_type）组合下的结果集 */
interface TaskBucket {
  taskId: number
  resultIds: number[]
}

/** 一个（用例 × 设备/API × result_type）组合 */
interface ResultNodeAgg {
  caseId: string
  deviceId: number | null
  apiId: number | null
  deviceKey: string
  /** 原始 result_type 取值（展示文案由 resultTypeLabel 兜底） */
  resultType: string
  resultTypeKey: string
  resultIds: number[]
  /** taskId → 该任务在本组合下的结果集（A 组任务末级数据源） */
  tasks: Map<number, TaskBucket>
}

interface TreeAggregate {
  nodes: ResultNodeAgg[]
  /** 全树任务集（阶段 1 已选任务，顺序同树） */
  taskIds: number[]
  /** 全树 result_type 原始取值（判多样性/省略层级） */
  resultTypes: (string | null)[]
  meta: TreeMetaIndex
  /** 整棵树只有 1 个任务 → 任务层省略 */
  omitTaskLayer: boolean
  /** 结果类型只有 1 种 → result_type 层省略 */
  omitResultTypeLayer: boolean
}

function aggregateTree(tree: PickCandidateTree): TreeAggregate {
  const meta = indexMeta(tree)
  const nodes = new Map<string, ResultNodeAgg>()
  const resultTypes: (string | null)[] = []

  for (const taskNode of tree.tree) {
    for (const caseNode of taskNode.cases) {
      for (const deviceNode of caseNode.devices) {
        const dk = deviceNodeKey(deviceNode.deviceId, deviceNode.apiId)
        for (const rtNode of deviceNode.resultTypes) {
          resultTypes.push(rtNode.resultType)
          const rk = resultTypeKey(rtNode.resultType)
          const key = `${caseNode.caseId}\u0000${dk}\u0000${rk}`
          let agg = nodes.get(key)
          if (!agg) {
            agg = {
              caseId: caseNode.caseId,
              deviceId: deviceNode.deviceId,
              apiId: deviceNode.apiId,
              deviceKey: dk,
              resultType: rtNode.resultType,
              resultTypeKey: rk,
              resultIds: [],
              tasks: new Map(),
            }
            nodes.set(key, agg)
          }
          agg.resultIds.push(...rtNode.resultIds)
          const bucket = agg.tasks.get(taskNode.taskId) ?? {
            taskId: taskNode.taskId,
            resultIds: [],
          }
          bucket.resultIds.push(...rtNode.resultIds)
          agg.tasks.set(taskNode.taskId, bucket)
        }
      }
    }
  }

  return {
    nodes: [...nodes.values()],
    taskIds: meta.taskIds,
    resultTypes,
    meta,
    omitTaskLayer: new Set(meta.taskIds).size <= 1,
    omitResultTypeLayer: !hasResultTypeVariety(resultTypes),
  }
}

/** 按 key 分组（保持首次出现顺序） */
function groupNodes<K extends string>(
  nodes: ResultNodeAgg[],
  keyOf: (node: ResultNodeAgg) => K
): Map<K, ResultNodeAgg[]> {
  const map = new Map<K, ResultNodeAgg[]>()
  for (const node of nodes) {
    const key = keyOf(node)
    const list = map.get(key) ?? []
    list.push(node)
    map.set(key, list)
  }
  return map
}

/** 组合节点全部结果 id（同组多 result_type 时取并集，保持首次出现顺序） */
function unionResultIds(nodes: ResultNodeAgg[]): number[] {
  const seen = new Set<number>()
  const ids: number[] = []
  for (const node of nodes) {
    for (const id of node.resultIds) {
      if (seen.has(id)) continue
      seen.add(id)
      ids.push(id)
    }
  }
  return ids
}

/** 任务名（meta 缺省落「任务 {id}」） */
function taskNameOf(meta: TreeMetaIndex, taskId: number): string {
  return meta.tasks.get(taskId)?.taskName?.trim() || `任务 ${taskId}`
}

/**
 * 叶前一级（A 组）：任务分支（level='task'，每个任务各自一个 leafFilter）
 * 或（单任务）直接挂叶——此时 leaf-parent 是调用方节点，结果由调用方携带 leafFilter。
 */
function taskLeafBranches(
  nodes: ResultNodeAgg[],
  agg: TreeAggregate,
  keyPrefix: string,
  scope: { caseId: string; deviceId: number | null; apiId: number | null }
): PickTreeItem[] {
  if (agg.omitTaskLayer) return []
  const buckets = new Map<number, number[]>()
  for (const node of nodes) {
    for (const [taskId, bucket] of node.tasks) {
      const ids = buckets.get(taskId) ?? []
      ids.push(...bucket.resultIds)
      buckets.set(taskId, ids)
    }
  }
  const branches: PickTreeBranch[] = []
  for (const [taskId, rawIds] of buckets) {
    const resultIds = [...new Set(rawIds)]
    branches.push({
      kind: 'branch',
      key: `${keyPrefix}-task:${taskId}`,
      level: 'task',
      name: taskNameOf(agg.meta, taskId),
      count: resultIds.length,
      resultIds,
      children: [],
      leafFilter: makeLeafFilter(
        [taskId],
        scope.caseId,
        scope.deviceId,
        scope.apiId,
        singleResultTypeOf(nodes)
      ),
    })
  }
  return branches
}

/**
 * 组内 result_type 取值（省略 result_type 层时用于叶过滤）：
 * 全组同一桶 → 该桶；跨桶 → null（不过滤，交由后端口径取全量）。
 */
function singleResultTypeOf(nodes: ResultNodeAgg[]): string | null {
  const values = new Set(nodes.map((n) => n.resultTypeKey))
  return values.size === 1 ? nodes[0]?.resultType ?? null : null
}

/** 叶父级节点的 leafFilter（单任务时挂到调用方节点上） */
function leafFilterOf(
  nodes: ResultNodeAgg[],
  agg: TreeAggregate,
  scope: { caseId: string; deviceId: number | null; apiId: number | null }
): PickLeafFilter {
  return makeLeafFilter(
    agg.taskIds,
    scope.caseId,
    scope.deviceId,
    scope.apiId,
    singleResultTypeOf(nodes)
  )
}

/** 用例节点（三视图共用：名称 + CaseIdBadge + 算法徽章 + 元信息 + 计数） */
function buildCaseNode(
  agg: TreeAggregate,
  caseId: string,
  count: number,
  resultIds: number[],
  children: PickTreeItem[],
  keyPrefix: string,
  leafFilter?: PickLeafFilter
): PickTreeBranch {
  const meta = agg.meta.cases.get(caseId)
  return {
    kind: 'branch',
    key: `${keyPrefix}:${caseId}`,
    level: 'case',
    name: displayCaseName(meta),
    caseId,
    ...caseBranchMeta(meta),
    count,
    resultIds,
    children,
    ...(leafFilter ? { leafFilter } : {}),
  }
}

/** 设备/API 节点（三视图共用） */
function buildDeviceNode(
  agg: TreeAggregate,
  nodes: ResultNodeAgg[],
  children: PickTreeItem[],
  key: string
): PickTreeBranch {
  const first = nodes[0]
  const name =
    first.deviceId != null
      ? displayDeviceName(agg.meta.devices.get(first.deviceId))
      : displayApiName(agg.meta.apis.get(first.apiId ?? -1))
  return {
    kind: 'branch',
    key,
    level: 'device',
    name,
    count: unionResultIds(nodes).length,
    resultIds: unionResultIds(nodes),
    children,
  }
}

/* ============================================================
 * 任务视角树（任务→用例卡→设备/API→result_type→叶；快捷加购弹窗使用）
 * ============================================================ */

/** 单任务子树（任务 → 用例 → 设备/API → result_type → 叶） */
function buildTaskNode(
  taskNode: PickTreeTaskNode,
  meta: TreeMetaIndex
): PickTreeBranch {
  const cases: PickTreeBranch[] = taskNode.cases.map((caseNode) => {
    const caseMeta = meta.cases.get(caseNode.caseId)
    const devices: PickTreeBranch[] = caseNode.devices.map((deviceNode) => {
      const dk = deviceNodeKey(deviceNode.deviceId, deviceNode.apiId)
      const resultTypes: PickTreeBranch[] = deviceNode.resultTypes.map((rtNode) => ({
        kind: 'branch',
        key: `rt:${taskNode.taskId}:${caseNode.caseId}:${dk}:${resultTypeKey(rtNode.resultType)}`,
        level: 'resultType',
        name: resultTypeLabel(rtNode.resultType),
        count: rtNode.resultIds.length,
        resultIds: rtNode.resultIds,
        children: [],
        leafFilter: makeLeafFilter(
          [taskNode.taskId],
          caseNode.caseId,
          deviceNode.deviceId,
          deviceNode.apiId,
          rtNode.resultType
        ),
      }))
      const deviceResultIds = [
        ...new Set(deviceNode.resultTypes.flatMap((rt) => rt.resultIds)),
      ]
      return {
        kind: 'branch' as const,
        key: `device:${taskNode.taskId}:${caseNode.caseId}:${dk}`,
        level: 'device' as const,
        name:
          deviceNode.deviceId != null
            ? displayDeviceName(meta.devices.get(deviceNode.deviceId))
            : displayApiName(meta.apis.get(deviceNode.apiId ?? -1)),
        count: deviceResultIds.length,
        resultIds: deviceResultIds,
        children: resultTypes,
      }
    })
    const caseResultIds = caseNode.devices.flatMap((d) =>
      d.resultTypes.flatMap((rt) => rt.resultIds)
    )
    return {
      kind: 'branch' as const,
      key: `case:${taskNode.taskId}:${caseNode.caseId}`,
      level: 'case' as const,
      name: displayCaseName(caseMeta),
      caseId: caseNode.caseId,
      ...caseBranchMeta(caseMeta),
      count: caseResultIds.length,
      resultIds: caseResultIds,
      children: devices,
    }
  })
  const taskResultIds = taskNode.cases.flatMap((c) =>
    c.devices.flatMap((d) => d.resultTypes.flatMap((rt) => rt.resultIds))
  )
  return {
    kind: 'branch',
    key: `task:${taskNode.taskId}`,
    level: 'task',
    name: taskNameOf(meta, taskNode.taskId),
    count: taskResultIds.length,
    resultIds: taskResultIds,
    children: cases,
  }
}

/** 任务视角树（阶段 2 快捷加购弹窗：单任务 / 少量任务时的五级层级） */
export function buildPickTaskTree(tree: PickCandidateTree | undefined): PickTreeBranch[] {
  if (!tree) return []
  const meta = indexMeta(tree)
  return tree.tree.map((taskNode) => buildTaskNode(taskNode, meta))
}

/* ============================================================
 * 三视图（用例 / 设备 / 结果类型，INT-1694 口径）：同一棵树重排
 * ============================================================ */

/**
 * 用例视图（A 组）：用例卡 → 设备/API → result_type → 任务 → 叶。
 * 第 1 层组织在 UI 侧由 PickCaseOrgList 聚合，domain 只给用例平铺；
 * 用例/设备/result_type 层跨任务共享，任务层在最末一级。
 */
export function buildPickCaseView(
  tree: PickCandidateTree | undefined
): PickTreeBranch[] {
  if (!tree) return []
  const agg = aggregateTree(tree)

  const cases: PickTreeBranch[] = []
  for (const [caseId, caseNodes] of groupNodes(agg.nodes, (n) => n.caseId)) {
    const devices: PickTreeBranch[] = []
    for (const [dk, deviceNodes] of groupNodes(caseNodes, (n) => n.deviceKey)) {
      const deviceKey = `pcv-device:${caseId}:${dk}`
      const scope = {
        caseId,
        deviceId: deviceNodes[0].deviceId,
        apiId: deviceNodes[0].apiId,
      }
      if (agg.omitResultTypeLayer) {
        const device = buildDeviceNode(
          agg,
          deviceNodes,
          taskLeafBranches(deviceNodes, agg, deviceKey, scope),
          deviceKey
        )
        if (agg.omitTaskLayer) {
          device.leafFilter = leafFilterOf(deviceNodes, agg, scope)
        }
        devices.push(device)
        continue
      }
      const resultTypes: PickTreeBranch[] = []
      for (const [rk, rtNodes] of groupNodes(deviceNodes, (n) => n.resultTypeKey)) {
        const rtKey = `pcv-resultType:${caseId}:${dk}:${rk}`
        resultTypes.push({
          kind: 'branch',
          key: rtKey,
          level: 'resultType',
          name: resultTypeLabel(rtNodes[0].resultType),
          count: unionResultIds(rtNodes).length,
          resultIds: unionResultIds(rtNodes),
          children: taskLeafBranches(rtNodes, agg, rtKey, scope),
          ...(agg.omitTaskLayer
            ? { leafFilter: leafFilterOf(rtNodes, agg, scope) }
            : {}),
        })
      }
      devices.push(buildDeviceNode(agg, deviceNodes, resultTypes, deviceKey))
    }
    const caseResultIds = unionResultIds(caseNodes)
    cases.push(
      buildCaseNode(agg, caseId, caseResultIds.length, caseResultIds, devices, 'pcv')
    )
  }
  return cases
}

/**
 * 设备视图（A 组）：设备/API → result_type → **用例层组织** → 用例卡 → 任务 → 叶。
 * 组织层是独立一层（分组/标签组头），平铺子视图下用例卡直挂组头；
 * result_type 只有 1 种时该层省略（设备/API → 组织层 → 用例卡）。
 */
export function buildPickDeviceView(
  tree: PickCandidateTree | undefined,
  org: PickCaseOrgDimension = 'group',
  subView: PickCaseOrgSubView = 'flat'
): PickTreeBranch[] {
  if (!tree) return []
  const agg = aggregateTree(tree)

  /** 用例卡集合（组织层之下，同一设备/result_type 内按 caseId 聚合） */
  const buildCases = (
    caseNodes: ResultNodeAgg[],
    prefix: string,
    dk: string
  ): PickTreeBranch[] => {
    const cases: PickTreeBranch[] = []
    for (const [caseId, caseGroup] of groupNodes(caseNodes, (n) => n.caseId)) {
      const caseKey = `${prefix}-case:${caseId}`
      const scope = {
        caseId,
        deviceId: caseGroup[0].deviceId,
        apiId: caseGroup[0].apiId,
      }
      const resultIds = unionResultIds(caseGroup)
      const children = taskLeafBranches(caseGroup, agg, caseKey, scope)
      cases.push(
        buildCaseNode(
          agg,
          caseId,
          resultIds.length,
          resultIds,
          children,
          `${prefix}:${dk}`,
          agg.omitTaskLayer ? leafFilterOf(caseGroup, agg, scope) : undefined
        )
      )
    }
    return cases
  }

  const devices: PickTreeBranch[] = []
  for (const [dk, deviceNodes] of groupNodes(agg.nodes, (n) => n.deviceKey)) {
    const deviceKey = `dv-device:${dk}`
    if (agg.omitResultTypeLayer) {
      devices.push(
        buildDeviceNode(
          agg,
          deviceNodes,
          buildCaseOrgBranches(
            buildCases(deviceNodes, `dv`, dk),
            org,
            subView,
            `dv-org:${dk}`
          ),
          deviceKey
        )
      )
      continue
    }
    const resultTypes: PickTreeBranch[] = []
    for (const [rk, rtNodes] of groupNodes(deviceNodes, (n) => n.resultTypeKey)) {
      resultTypes.push({
        kind: 'branch',
        key: `dv-resultType:${dk}:${rk}`,
        level: 'resultType',
        name: resultTypeLabel(rtNodes[0].resultType),
        count: unionResultIds(rtNodes).length,
        resultIds: unionResultIds(rtNodes),
        // 组织层：result_type 之下、用例卡之上（分组/标签组头 → 用例卡）
        children: buildCaseOrgBranches(
          buildCases(rtNodes, `dv-${rk}`, dk),
          org,
          subView,
          `dv-org:${dk}:${rk}`
        ),
      })
    }
    devices.push(buildDeviceNode(agg, deviceNodes, resultTypes, deviceKey))
  }
  return devices
}

/**
 * 结果类型视图（A 组）：result_type → 设备/API → **用例层组织** → 用例卡 → 任务 → 叶。
 * 组织层位置与设备视图一致（result_type 之下的设备节点之后、用例卡之前）。
 */
export function buildPickResultTypeView(
  tree: PickCandidateTree | undefined,
  org: PickCaseOrgDimension = 'group',
  subView: PickCaseOrgSubView = 'flat'
): PickTreeBranch[] {
  if (!tree) return []
  const agg = aggregateTree(tree)

  const resultTypes: PickTreeBranch[] = []
  for (const [rk, rtNodes] of groupNodes(agg.nodes, (n) => n.resultTypeKey)) {
    const devices: PickTreeBranch[] = []
    for (const [dk, deviceNodes] of groupNodes(rtNodes, (n) => n.deviceKey)) {
      const cases: PickTreeBranch[] = []
      for (const [caseId, caseGroup] of groupNodes(deviceNodes, (n) => n.caseId)) {
        const casePrefix = `rtv-${rk}-${dk}`
        const caseKey = `${casePrefix}-task`
        const scope = {
          caseId,
          deviceId: caseGroup[0].deviceId,
          apiId: caseGroup[0].apiId,
        }
        const resultIds = unionResultIds(caseGroup)
        cases.push(
          buildCaseNode(
            agg,
            caseId,
            resultIds.length,
            resultIds,
            taskLeafBranches(caseGroup, agg, caseKey, scope),
            casePrefix,
            agg.omitTaskLayer ? leafFilterOf(caseGroup, agg, scope) : undefined
          )
        )
      }
      devices.push(
        buildDeviceNode(
          agg,
          deviceNodes,
          // 组织层：设备/API 之下、用例卡之上（与设备视图同一层级语义）
          buildCaseOrgBranches(cases, org, subView, `rtv-org:${rk}:${dk}`),
          `rtv-device:${rk}:${dk}`
        )
      )
    }
    resultTypes.push({
      kind: 'branch',
      key: `rtv-resultType:${rk}`,
      level: 'resultType',
      name: resultTypeLabel(rtNodes[0].resultType),
      count: unionResultIds(rtNodes).length,
      resultIds: unionResultIds(rtNodes),
      children: devices,
    })
  }
  return resultTypes
}

/** 结果类型维度是否具备多样性（种类 <2 时「结果类型视图」入口不渲染，树内省略该层） */
export function treeResultTypeVariety(tree: PickCandidateTree | undefined): boolean {
  if (!tree) return false
  const values: (string | null)[] = []
  for (const taskNode of tree.tree) {
    for (const caseNode of taskNode.cases) {
      for (const deviceNode of caseNode.devices) {
        for (const rtNode of deviceNode.resultTypes) values.push(rtNode.resultType)
      }
    }
  }
  return hasResultTypeVariety(values)
}

/* ============================================================
 * 已选规模统计（§3.3 已选汇总条）
 * ============================================================ */

export interface SelectionStats {
  results: number
  tasks: number
  devices: number
  cases: number
}

/** 结果 id → 归属（任务/用例/设备）索引（统计不依赖叶明细是否加载） */
export interface PickResultIndexEntry {
  taskId: number
  taskName: string
  caseId: string
  caseName: string
  deviceKey: string
  deviceName: string
}

/** 由候选树构建结果归属索引（3614 行规模，一次 O(n)） */
export function buildResultIndex(
  tree: PickCandidateTree | undefined
): Map<number, PickResultIndexEntry> {
  const index = new Map<number, PickResultIndexEntry>()
  if (!tree) return index
  const meta = indexMeta(tree)
  for (const taskNode of tree.tree) {
    const taskName = taskNameOf(meta, taskNode.taskId)
    for (const caseNode of taskNode.cases) {
      const caseName = displayCaseName(meta.cases.get(caseNode.caseId))
      for (const deviceNode of caseNode.devices) {
        const deviceName =
          deviceNode.deviceId != null
            ? displayDeviceName(meta.devices.get(deviceNode.deviceId))
            : displayApiName(meta.apis.get(deviceNode.apiId ?? -1))
        const dk = deviceNodeKey(deviceNode.deviceId, deviceNode.apiId)
        for (const rtNode of deviceNode.resultTypes) {
          for (const resultId of rtNode.resultIds) {
            index.set(resultId, {
              taskId: taskNode.taskId,
              taskName,
              caseId: caseNode.caseId,
              caseName,
              deviceKey: dk,
              deviceName,
            })
          }
        }
      }
    }
  }
  return index
}

/** 汇总条数据（结果 / 来源任务 / 设备 / 用例；按已选集合与树索引统计，与视图无关） */
export function computeSelectionStatsFromIndex(
  index: ReadonlyMap<number, PickResultIndexEntry>,
  selectedIds: ReadonlySet<number>
): SelectionStats {
  const stats: SelectionStats = { results: 0, tasks: 0, devices: 0, cases: 0 }
  const taskSet = new Set<number>()
  const deviceSet = new Set<string>()
  const caseSet = new Set<string>()
  for (const resultId of selectedIds) {
    const entry = index.get(resultId)
    if (!entry) continue
    stats.results += 1
    taskSet.add(entry.taskId)
    deviceSet.add(entry.deviceKey)
    caseSet.add(entry.caseId)
  }
  stats.tasks = taskSet.size
  stats.devices = deviceSet.size
  stats.cases = caseSet.size
  return stats
}

/**
 * 反选当前筛选：树根节点的 resultIds 即各分支的完整结果集（服务端给的，与叶是否加载无关），
 * 按唯一 resultId 恰好翻转一次（标签视图下同一结果会挂在多个组下）。
 */
export function invertVisibleSelection(
  items: PickTreeItem[],
  selectedIds: ReadonlySet<number>
): Set<number> {
  const next = new Set(selectedIds)
  const ids = new Set<number>()
  for (const item of items) {
    if (item.kind !== 'branch') continue
    for (const id of item.resultIds) ids.add(id)
  }
  for (const id of ids) {
    if (next.has(id)) next.delete(id)
    else next.add(id)
  }
  return next
}

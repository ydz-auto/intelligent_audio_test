/**
 * 挑选树勾选联动与用例层组织（18_挑选合并功能交互重设计.md §3.1-§3.2，INT-600）。
 * 联动规则 R1-R10 全部在此实现并单测；组件仅消费，不重算。
 * 阶段 2 三视图/任务树的构建在 `pick-candidate-tree.ts`（服务端候选树为唯一骨架源）。
 * 依赖规则：domain 零依赖。
 */
import type {
  CartTreeBranch,
  CartTreeItem,
  CartTreeLeaf,
  PickCartEntry,
  PickCartGroup,
  PickCaseOrgDimension,
  PickCaseOrgSubView,
  PickLevel,
  PickTreeBranch,
  PickTreeItem,
  PickTreeLeaf,
  SelectionState,
} from '@/domain/models/cherryPick'
import {
  groupCasesByCaseGroup,
  groupCasesByTag,
  type CaseSubGroup,
  type SubViewCaseItem,
} from '@/domain/lib/sub-view-aggregation'

/* ============================================================
 * 名称缺省降级与缺值桶（§11-2 + INT-713 打回 #1）
 * 候选/条目未返名称时不裸显 36 位 UUID，改友好文案 + 截断 id。
 * ============================================================ */

const CASE_UNAVAILABLE = '用例不可用'
const DEVICE_UNAVAILABLE = '设备不可用'
const API_UNAVAILABLE = 'API不可用'

/** 截断 id 前 8 位（友好降级展示用） */
function shortId(id: string | null | undefined): string {
  const raw = id?.trim()
  if (!raw) return '未知'
  return raw.length > 8 ? `${raw.slice(0, 8)}…` : raw
}

/** 用例名缺省：友好文案 + 截断 case_id（不裸显 UUID） */
function caseDisplayName(name: string | null, caseId: string | null): string {
  if (name && name.trim()) return name
  return `${CASE_UNAVAILABLE} ${shortId(caseId)}`
}

/** 设备/API 组名缺省：友好文案 + 截断 id（设备/API 二选一） */
function deviceGroupDisplayName(
  name: string | null,
  deviceId: number | null,
  apiId: number | null
): string {
  if (name && name.trim()) return name
  if (deviceId != null) return `${DEVICE_UNAVAILABLE} ${shortId(String(deviceId))}`
  if (apiId != null) return `${API_UNAVAILABLE} ${shortId(String(apiId))}`
  return '不可用'
}

/** §11-5 条目快照无 source_result_type → result_type 级分组折叠为「结果类型待补充」 */
export const PENDING_RESULT_TYPE_KEY = '__pending__'
export const PENDING_RESULT_TYPE_LABEL = '结果类型待补充'

/* ============================================================
 * 用例层组织层（A 组三视图与购物车共用）
 * INT-1694 三次口径：result_type（或设备/API）之后、用例卡之前插入组织层。
 * 阶段 2 三视图（用例/设备/结果类型）的树骨架由 `pick-candidate-tree.ts`
 * 从服务端候选树构建，本文件只提供组织层聚合与勾选联动（R1-R10）。
 * ============================================================ */

/** 按任务分簇（A 组末端任务层共用；任务按首次出现、任务内按原顺序） */
function groupRowsBySourceTask<Row>(
  rows: readonly Row[],
  taskIdOf: (row: Row) => number,
  taskNameOf: (row: Row) => string | null | undefined
): { taskId: number; taskName: string; rows: Row[] }[] {
  const taskMap = new Map<number, Row[]>()
  for (const row of rows) {
    const taskId = taskIdOf(row)
    const list = taskMap.get(taskId) ?? []
    list.push(row)
    taskMap.set(taskId, list)
  }
  return [...taskMap].map(([taskId, list]) => ({
    taskId,
    taskName: taskNameOf(list[0])?.trim() || `任务 ${taskId}`,
    rows: list,
  }))
}

/* ============================================================
 * 用例层组织（组织层独立一层，INT-1694 三次口径 2026-10-24T03:51Z）
 * 设备 / 结果类型视图（A 组）与任务视图设备 / 结果类型子模式（B 组）：
 * result_type（或设备/API）之后、用例卡之前插入组织层——
 *   分组视图 / 标签视图（orgKind）+ 平铺 / 交叉（交叉时组内再按另一维度分子组）。
 * 组织组头 = 普通分支节点（名称 + 计数 + 三态 Checkbox + 展开/收起 + 移除该组），
 * 组内挂用例卡节点。组织状态为会话态（usePickOrg），只影响视觉分组，
 * 不改变勾选联动与 selectedResultIds / selectedEntryIds。
 * 平铺子视图下组内直接挂用例卡（不再出子组头），层级语义不变。
 * ============================================================ */

/** 组织聚合入参（用例级分支携带 §11-7 真名，字段缺省才落兜底桶） */
interface CaseOrgEntry<B> extends SubViewCaseItem {
  branch: B
}

/** 用例卡集合 → 组织分组（分组视图 / 标签视图；复用 sub-view-aggregation 同款语义） */
function groupCaseOrgEntries<B>(
  cases: CaseOrgEntry<B>[],
  orgKind: PickCaseOrgDimension
): CaseSubGroup<CaseOrgEntry<B>>[] {
  return orgKind === 'group'
    ? groupCasesByCaseGroup(cases)
    : groupCasesByTag(cases, [])
}

/** 交叉子视图的下一维度（分组视图内按标签、标签视图内按用例分组） */
function crossOrgKind(orgKind: PickCaseOrgDimension): PickCaseOrgDimension {
  return orgKind === 'group' ? 'tag' : 'group'
}

function toPickCaseOrgEntries(cases: PickTreeBranch[]): CaseOrgEntry<PickTreeBranch>[] {
  return cases.map((b) => ({
    branch: b,
    tags: b.tags ?? [],
    groupId: b.groupId ?? null,
    groupName: b.groupName ?? null,
    totalDuration: b.totalDuration ?? null,
  }))
}

function toCartCaseOrgEntries(
  cases: CartTreeBranch[]
): CaseOrgEntry<CartTreeBranch>[] {
  return cases.map((b) => ({
    branch: b,
    tags: b.tags ?? [],
    groupId: b.groupId ?? null,
    groupName: b.groupName ?? null,
    totalDuration: b.totalDuration ?? null,
  }))
}

/** 组织组头节点（名称取分组名 / 标签名 / 兜底桶名；计数 = 组内结果条数并集） */
function pickCaseOrgLevel(
  cases: PickTreeBranch[],
  orgKind: PickCaseOrgDimension,
  subView: PickCaseOrgSubView,
  keyPrefix: string
): PickTreeItem[] {
  const groups = groupCaseOrgEntries(toPickCaseOrgEntries(cases), orgKind)
  return groups.map((g) => {
    const groupCases = g.cases.map((c) => c.branch)
    const key = `${keyPrefix}-org:${orgKind}:${g.key}`
    const resultIds = [
      ...new Set(groupCases.flatMap((b) => b.resultIds)),
    ]
    return {
      kind: 'branch' as const,
      key,
      level: 'caseOrg' as const,
      orgKind,
      name: g.label,
      count: resultIds.length,
      resultIds,
      children:
        subView === 'flat'
          ? groupCases
          : pickCaseOrgLevel(
              groupCases,
              crossOrgKind(orgKind),
              'flat',
              key
            ),
    }
  })
}

/**
 * 设备 / 结果类型视图（A 组）组织层：用例卡集合同一 org 维度聚成组头分支，
 * 组头下挂用例卡（交叉子视图时组内再按另一维度分子组）。
 * 组织只影响视觉分组，resultIds 并集保证组头勾选 = 组内全部结果（不跨节点）。
 */
export function buildCaseOrgBranches(
  cases: PickTreeBranch[],
  org: PickCaseOrgDimension = 'group',
  subView: PickCaseOrgSubView = 'flat',
  keyPrefix = 'org'
): PickTreeItem[] {
  return pickCaseOrgLevel(cases, org, subView, keyPrefix)
}

/** 购物车组织层（A 组设备/结果类型视图 + B 组设备/结果类型子模式共用） */
function cartCaseOrgLevel(
  cases: CartTreeBranch[],
  orgKind: PickCaseOrgDimension,
  subView: PickCaseOrgSubView,
  keyPrefix: string
): CartTreeItem[] {
  const groups = groupCaseOrgEntries(toCartCaseOrgEntries(cases), orgKind)
  return groups.map((g) => {
    const groupCases = g.cases.map((c) => c.branch)
    const key = `${keyPrefix}-org:${orgKind}:${g.key}`
    const entryIds = [...new Set(groupCases.flatMap((b) => b.entryIds))]
    return {
      kind: 'branch' as const,
      key,
      level: 'caseOrg' as const,
      orgKind,
      name: g.label,
      count: entryIds.length,
      entryIds,
      children:
        subView === 'flat'
          ? groupCases
          : cartCaseOrgLevel(groupCases, crossOrgKind(orgKind), 'flat', key),
    }
  })
}

/* ============================================================
 * 三态联动（R1-R5/R10）
 * ============================================================ */

/** 节点勾选态（R3：全部直接子级选中转全选；部分选中 indeterminate） */
export function getBranchSelectionState(
  branch: PickTreeBranch,
  selectedIds: ReadonlySet<number>
): SelectionState {
  if (branch.resultIds.length === 0) return 'unchecked'
  let selected = 0
  for (const id of branch.resultIds) {
    if (selectedIds.has(id)) selected += 1
  }
  if (selected === branch.resultIds.length) return 'checked'
  if (selected > 0) return 'indeterminate'
  return 'unchecked'
}

/**
 * 勾选/取消父级 → 全部子孙选中/取消（R1/R2）。
 * R4 取消 device：其下 result_type 与结果行全部取消（容器语义）。
 * R5 取消 result_type：仅清其下结果行，父 device 自动转部分选中。
 * R6/R7 用例/任务级勾选 = 选中其下全部（跨设备/结果类型全含）。
 */
export function toggleBranchSelection(
  branch: PickTreeBranch,
  selectedIds: ReadonlySet<number>,
  select: boolean
): Set<number> {
  const next = new Set(selectedIds)
  for (const id of branch.resultIds) {
    if (select) next.add(id)
    else next.delete(id)
  }
  return next
}

/** 叶行勾选（仅该 result_id） */
export function toggleLeafSelection(
  leaf: PickTreeLeaf,
  selectedIds: ReadonlySet<number>
): Set<number> {
  const next = new Set(selectedIds)
  if (next.has(leaf.resultId)) next.delete(leaf.resultId)
  else next.add(leaf.resultId)
  return next
}

/** 清空选择 */
export function clearSelection(): Set<number> {
  return new Set()
}

/* ============================================================
 * 购物车树构建（INT-1694 二次口径，负责人 2026-10-24）
 * A 组（用例 / 设备 / 结果类型三视图）：任务在最末一级（叶的前一级），
 *     任务之上的节点跨任务共享、key 不带 taskId 命名空间；
 * B 组（任务视图，购物车 / 复核抽屉默认）：任务在第一级，任务下按子模式
 *     （用例 / 设备 / 结果类型）展开，子树 key 带 taskId 命名空间。
 * 无 taskId 命名空间的 A 组同样按「整棵树只有 1 个任务」省略任务层。
 * result_type 级分组受 §11-5 限制：条目快照无 source_result_type 时折叠缺省。
 * ============================================================ */

/** 购物车条目 → case 分组 key（缺失折叠 unknown） */
function cartCaseKey(e: PickCartEntry): string {
  return e.sourceCaseId ?? 'unknown'
}

/** 购物车条目 → 设备/API 分组 key（device_id 与 api_id 二选一，实测） */
function cartDeviceKey(e: PickCartEntry): string {
  return e.sourceDeviceId != null
    ? `device:${e.sourceDeviceId}`
    : `api:${e.sourceApiId ?? '?'}`
}

/** 购物车条目 → result_type 分组 key（缺省折叠「结果类型待补充」，§11-5） */
function cartResultTypeKey(e: PickCartEntry): string {
  return e.sourceResultType && e.sourceResultType.trim()
    ? e.sourceResultType
    : PENDING_RESULT_TYPE_KEY
}

/** 按 key 分组（保持首次出现顺序） */
function groupEntries<K extends string>(
  entries: PickCartEntry[],
  keyOf: (e: PickCartEntry) => K
): Map<K, PickCartEntry[]> {
  const map = new Map<K, PickCartEntry[]>()
  for (const e of entries) {
    const k = keyOf(e)
    const list = map.get(k) ?? []
    list.push(e)
    map.set(k, list)
  }
  return map
}

/** 购物车叶行构造（任务维度已是树内分支，叶不再携带来源任务名消歧） */
function buildCartLeaf(e: PickCartEntry): CartTreeLeaf {
  return {
    kind: 'leaf',
    key: `cart-leaf:${e.itemId}`,
    entryId: e.itemId,
    caseName: caseDisplayName(e.sourceCaseName, e.sourceCaseId),
    deviceName: e.sourceDeviceName,
    apiName: e.sourceApiName,
    resultType: e.sourceResultType,
    executionStatus: e.executionStatus,
    evaluationStatus: e.evaluationStatus,
    invalid: e.invalid,
    sourceTaskId: e.sourceTaskId,
    sourceTaskName: e.sourceTaskName,
  }
}

/**
 * A 组末端任务层：条目按 source_task_id 分簇 → 任务分支（level='task'，
 * 名取 source_task_name）→ 叶。omitTaskLayer=true（整棵树只有 1 个任务）时直接返回叶。
 */
export function buildCartTaskLeafBranches(
  entries: PickCartEntry[],
  keyPrefix: string,
  omitTaskLayer = false
): CartTreeItem[] {
  if (omitTaskLayer) return entries.map(buildCartLeaf)
  return groupRowsBySourceTask(
    entries,
    (e) => e.sourceTaskId,
    (e) => e.sourceTaskName
  ).map((cluster) => ({
    kind: 'branch' as const,
    key: `${keyPrefix}-task:${cluster.taskId}`,
    level: 'task' as const,
    name: cluster.taskName,
    count: cluster.rows.length,
    entryIds: cluster.rows.map((e) => e.itemId),
    children: cluster.rows.map(buildCartLeaf),
  }))
}

/** 叶前一级：任务层（A 组）或直挂叶 */
function cartLeafLayer(
  entries: PickCartEntry[],
  keyPrefix: string,
  taskLayer: boolean,
  omitTaskLayer: boolean
): CartTreeItem[] {
  return taskLayer
    ? buildCartTaskLeafBranches(entries, keyPrefix, omitTaskLayer)
    : entries.map(buildCartLeaf)
}

/** 节点子层构造（视图决定下一层是什么） */
type CartChildBuilder = (entries: PickCartEntry[], nodeKey: string) => CartTreeItem[]

/** 用例节点（children 由视图决定：用例视图=设备层；设备/结果类型视图=叶前任务层） */
function buildCartCaseNode(
  entries: PickCartEntry[],
  keyPrefix: string,
  buildChildren: CartChildBuilder
): CartTreeBranch {
  const first = entries[0]
  const key = `${keyPrefix}-case:${cartCaseKey(first)}`
  return {
    kind: 'branch',
    key,
    level: 'case',
    name: caseDisplayName(first?.sourceCaseName, first?.sourceCaseId ?? null),
    caseId: first?.sourceCaseId ?? undefined,
    // INT-1693 落地后 adapter 填上 sourceTags/sourceGroup* → 组织层自动出真名，树结构不变
    tags: first?.sourceTags ?? [],
    groupId: first?.sourceGroupId ?? null,
    groupName: first?.sourceGroupName ?? null,
    totalDuration: first?.sourceTotalDuration ?? null,
    rounds: first?.sourceRounds ?? null,
    count: entries.length,
    entryIds: entries.map((e) => e.itemId),
    children: buildChildren(entries, key),
  }
}

/** 设备/API 节点（children 由视图决定：用例/设备视图=result_type 层；结果类型视图=用例层） */
function buildCartDeviceNode(
  entries: PickCartEntry[],
  keyPrefix: string,
  buildChildren: CartChildBuilder
): CartTreeBranch {
  const first = entries[0]
  const key = `${keyPrefix}-device:${cartDeviceKey(first)}`
  return {
    kind: 'branch',
    key,
    level: 'device',
    name: deviceGroupDisplayName(
      first?.sourceDeviceName ?? first?.sourceApiName ?? null,
      first?.sourceDeviceId ?? null,
      first?.sourceApiId ?? null
    ),
    count: entries.length,
    entryIds: entries.map((e) => e.itemId),
    children: buildChildren(entries, key),
  }
}

/** result_type 节点（children 由视图决定） */
function buildCartResultTypeNode(
  entries: PickCartEntry[],
  keyPrefix: string,
  buildChildren: CartChildBuilder
): CartTreeBranch {
  const rt = cartResultTypeKey(entries[0])
  const key = `${keyPrefix}-resultType:${rt}`
  return {
    kind: 'branch',
    key,
    level: 'resultType',
    name: rt === PENDING_RESULT_TYPE_KEY ? PENDING_RESULT_TYPE_LABEL : rt,
    count: entries.length,
    entryIds: entries.map((e) => e.itemId),
    children: buildChildren(entries, key),
  }
}

/** 用例视图形状：用例 → 设备/API → result_type → (任务层 | 叶)
 *  （result_type 只有 1 种时省略该层：用例 → 设备/API → (任务层 | 叶)） */
function cartCaseViewNodes(
  entries: PickCartEntry[],
  keyPrefix: string,
  taskLayer: boolean,
  omitTaskLayer: boolean,
  omitResultTypeLayer = false
): CartTreeBranch[] {
  const cases: CartTreeBranch[] = []
  for (const caseRows of groupEntries(entries, cartCaseKey).values()) {
    cases.push(
      buildCartCaseNode(caseRows, keyPrefix, (rows, caseKey) => {
        const devices: CartTreeItem[] = []
        for (const deviceRows of groupEntries(rows, cartDeviceKey).values()) {
          devices.push(
            buildCartDeviceNode(deviceRows, caseKey, (dRows, deviceKey) => {
              if (omitResultTypeLayer) {
                return cartLeafLayer(dRows, deviceKey, taskLayer, omitTaskLayer)
              }
              const resultTypes: CartTreeItem[] = []
              for (const rtRows of groupEntries(dRows, cartResultTypeKey).values()) {
                resultTypes.push(
                  buildCartResultTypeNode(rtRows, deviceKey, (leafRows, rtKey) =>
                    cartLeafLayer(leafRows, rtKey, taskLayer, omitTaskLayer)
                  )
                )
              }
              return resultTypes
            })
          )
        }
        return devices
      })
    )
  }
  return cases
}

/**
 * 设备视图形状：设备/API → result_type → **用例层组织** → 用例 → (任务层 | 叶)
 * （A 组购物车设备视图与 B 组任务视图设备子模式共用；组织层独立一层）
 * result_type 只有 1 种时省略该层：设备/API → 组织层 → 用例。
 */
function cartDeviceViewNodes(
  entries: PickCartEntry[],
  keyPrefix: string,
  taskLayer: boolean,
  omitTaskLayer: boolean,
  org: PickCaseOrgDimension = 'group',
  subView: PickCaseOrgSubView = 'flat',
  omitResultTypeLayer = false
): CartTreeBranch[] {
  /** 用例卡集合（组织层之下） */
  const buildCases = (rows: PickCartEntry[], prefix: string): CartTreeBranch[] => {
    const cases: CartTreeBranch[] = []
    for (const caseRows of groupEntries(rows, cartCaseKey).values()) {
      cases.push(
        buildCartCaseNode(caseRows, prefix, (leafRows, caseKey) =>
          cartLeafLayer(leafRows, caseKey, taskLayer, omitTaskLayer)
        )
      )
    }
    return cases
  }

  const devices: CartTreeBranch[] = []
  for (const deviceRows of groupEntries(entries, cartDeviceKey).values()) {
    devices.push(
      buildCartDeviceNode(deviceRows, keyPrefix, (rows, deviceKey) => {
        if (omitResultTypeLayer) {
          return cartCaseOrgLevel(
            buildCases(rows, deviceKey),
            org,
            subView,
            deviceKey
          )
        }
        const resultTypes: CartTreeItem[] = []
        for (const rtRows of groupEntries(rows, cartResultTypeKey).values()) {
          resultTypes.push(
            buildCartResultTypeNode(rtRows, deviceKey, (rtRowList, rtKey) =>
              // 组织层：result_type 之下、用例卡之上
              cartCaseOrgLevel(buildCases(rtRowList, rtKey), org, subView, rtKey)
            )
          )
        }
        return resultTypes
      })
    )
  }
  return devices
}

/**
 * 结果类型视图形状：result_type → 设备/API → **用例层组织** → 用例 → (任务层 | 叶)
 * （A 组购物车结果类型视图与 B 组任务视图结果类型子模式共用）
 */
function cartResultTypeViewNodes(
  entries: PickCartEntry[],
  keyPrefix: string,
  taskLayer: boolean,
  omitTaskLayer: boolean,
  org: PickCaseOrgDimension = 'group',
  subView: PickCaseOrgSubView = 'flat'
): CartTreeBranch[] {
  const resultTypes: CartTreeBranch[] = []
  for (const rtRows of groupEntries(entries, cartResultTypeKey).values()) {
    resultTypes.push(
      buildCartResultTypeNode(rtRows, keyPrefix, (rows, rtKey) => {
        const devices: CartTreeItem[] = []
        for (const deviceRows of groupEntries(rows, cartDeviceKey).values()) {
          devices.push(
            buildCartDeviceNode(deviceRows, rtKey, (dRows, deviceKey) => {
              const cases: CartTreeBranch[] = []
              for (const caseRows of groupEntries(dRows, cartCaseKey).values()) {
                cases.push(
                  buildCartCaseNode(caseRows, deviceKey, (leafRows, caseKey) =>
                    cartLeafLayer(leafRows, caseKey, taskLayer, omitTaskLayer)
                  )
                )
              }
              // 组织层：设备/API 之下、用例卡之上
              return cartCaseOrgLevel(cases, org, subView, deviceKey)
            })
          )
        }
        return devices
      })
    )
  }
  return resultTypes
}

/** 购物车条目全集（三视图跨任务共享同一 entryId 集） */
function cartEntriesOf(groups: PickCartGroup[]): PickCartEntry[] {
  return groups.flatMap((g) => g.entries)
}

/** 购物车结果类型种类 <2 → 树内省略 result_type 层（与「结果类型视图」入口同一判定） */
function cartOmitResultTypeLayer(groups: PickCartGroup[]): boolean {
  return !hasResultTypeVariety(
    cartEntriesOf(groups).map((e) => e.sourceResultType)
  )
}

/**
 * 结果类型维度是否具备多样性：种类 <2 时「结果类型视图」入口不渲染
 * （负责人 2026-10-24T12:39Z 追加口径；真实库 result_type 全为 default 时该视图与默认视图同形）。
 * null / 空串折叠成「结果类型待补充」兜底桶，与树内分组口径一致，同样计入种类。
 */
export function hasResultTypeVariety(
  resultTypes: readonly (string | null | undefined)[]
): boolean {
  const seen = new Set<string>()
  for (const resultType of resultTypes) {
    seen.add((resultType ?? '').trim() || PENDING_RESULT_TYPE_KEY)
    if (seen.size >= 2) return true
  }
  return false
}

/**
 * 购物车用例视图（A 组）：用例（PickCaseCard）→ 设备/API → result_type → 任务 → 叶。
 * 购物车 / 复核抽屉恒显任务层（单任务也不省略，与阶段 2 单任务省略口径相反）；
 * 结果类型只有 1 种时 result_type 层省略（用例 → 设备/API → 任务 → 叶）。
 */
export function buildCartCaseView(groups: PickCartGroup[]): CartTreeBranch[] {
  return cartCaseViewNodes(
    cartEntriesOf(groups),
    'cv',
    true,
    false,
    cartOmitResultTypeLayer(groups)
  )
}

/** 购物车设备视图（A 组）：设备/API → result_type → 组织层 → 用例（PickCaseCard）→ 任务 → 叶
 *  （结果类型只有 1 种时 result_type 层省略：设备/API → 组织层 → 用例 → 任务 → 叶） */
export function buildCartDeviceView(
  groups: PickCartGroup[],
  org: PickCaseOrgDimension = 'group',
  subView: PickCaseOrgSubView = 'flat'
): CartTreeBranch[] {
  return cartDeviceViewNodes(
    cartEntriesOf(groups),
    'dv',
    true,
    false,
    org,
    subView,
    cartOmitResultTypeLayer(groups)
  )
}

/** 购物车结果类型视图（A 组）：result_type → 设备/API → 组织层 → 用例（PickCaseCard）→ 任务 → 叶 */
export function buildCartResultTypeView(
  groups: PickCartGroup[],
  org: PickCaseOrgDimension = 'group',
  subView: PickCaseOrgSubView = 'flat'
): CartTreeBranch[] {
  return cartResultTypeViewNodes(
    cartEntriesOf(groups),
    'rtv',
    true,
    false,
    org,
    subView
  )
}

/** 任务视图子模式（任务下再分三视图，负责人 2026-10-24 口径 B 组） */
export type CartTaskSubView = 'case' | 'device' | 'resultType'

/**
 * 购物车任务视图（B 组，默认视图）：任务（第一级）→ 子模式展开——
 * 用例：用例层组织（组件 PickCaseOrgList 消费的用例分支）→ 用例卡 → 设备/API → result_type → 叶；
 * 设备：设备/API → result_type → **组织层** → 用例 → 叶；
 * 结果类型：result_type → 设备/API → **组织层** → 用例 → 叶。
 * 任务节点是最外层，故子树内不再插任务层（taskLayer=false），key 带 taskId 命名空间。
 * 组织层为任务内组织（不跨任务聚合），org 会话态与 A 组三视图共用同一份。
 */
export function buildCartTaskView(
  groups: PickCartGroup[],
  subView: CartTaskSubView = 'case',
  org: PickCaseOrgDimension = 'group',
  caseOrgSubView: PickCaseOrgSubView = 'flat'
): CartTreeBranch[] {
  return groups.map((group) => {
    const keyPrefix = `tv${group.taskId}`
    /** 结果类型种类按全集判定（跨任务同一口径），单种类时任务内也不渲染该层 */
    const omitResultTypeLayer = cartOmitResultTypeLayer(groups)
    const children: CartTreeItem[] =
      subView === 'case'
        ? cartCaseViewNodes(
            group.entries,
            keyPrefix,
            false,
            false,
            omitResultTypeLayer
          )
        : subView === 'device'
          ? cartDeviceViewNodes(
              group.entries,
              keyPrefix,
              false,
              false,
              org,
              caseOrgSubView,
              omitResultTypeLayer
            )
          : cartResultTypeViewNodes(
              group.entries,
              keyPrefix,
              false,
              false,
              org,
              caseOrgSubView
            )
    return {
      kind: 'branch' as const,
      key: `cart-task:${group.taskId}`,
      level: 'task' as const,
      name: group.taskName,
      count: group.entries.length,
      entryIds: group.entries.map((e) => e.itemId),
      children,
    }
  })
}

/** 收集购物车树节点全部条目 id（移除矩阵：节点/整组批量移除，§4.3） */
export function collectEntryIds(items: CartTreeItem[]): string[] {
  const ids: string[] = []
  const walk = (nodes: CartTreeItem[]) => {
    for (const item of nodes) {
      if (item.kind === 'leaf') ids.push(item.entryId)
      else walk(item.children)
    }
  }
  walk(items)
  // 标签视图下同一用例挂在多个标签组下，同一 entryId 会出现多次；
  // 移除矩阵按唯一 id 提交（「移除该组」的条数与载荷同一口径，不因视觉重复翻倍）。
  return [...new Set(ids)]
}

/** 购物车树三态勾选态（批量移除选择用） */
export function getCartBranchSelectionState(
  branch: CartTreeBranch,
  selectedEntryIds: ReadonlySet<string>
): SelectionState {
  if (branch.entryIds.length === 0) return 'unchecked'
  let selected = 0
  for (const id of branch.entryIds) {
    if (selectedEntryIds.has(id)) selected += 1
  }
  if (selected === branch.entryIds.length) return 'checked'
  if (selected > 0) return 'indeterminate'
  return 'unchecked'
}

/** 勾选/取消购物车节点（批量移除选择，R1-R5 同构） */
export function toggleCartBranchSelection(
  branch: CartTreeBranch,
  selectedEntryIds: ReadonlySet<string>,
  select: boolean
): Set<string> {
  const next = new Set(selectedEntryIds)
  for (const id of branch.entryIds) {
    if (select) next.add(id)
    else next.delete(id)
  }
  return next
}

/** 勾选/取消购物车叶（单条移除选择） */
export function toggleCartLeafSelection(
  leaf: CartTreeLeaf,
  selectedEntryIds: ReadonlySet<string>
): Set<string> {
  const next = new Set(selectedEntryIds)
  if (next.has(leaf.entryId)) next.delete(leaf.entryId)
  else next.add(leaf.entryId)
  return next
}

/** 层级中文名（§9：节点行文案） */
export const PICK_LEVEL_LABELS: Record<PickLevel, string> = {
  task: '任务',
  case: '用例',
  device: '设备',
  resultType: '结果类型',
  caseOrg: '用例组织',
}

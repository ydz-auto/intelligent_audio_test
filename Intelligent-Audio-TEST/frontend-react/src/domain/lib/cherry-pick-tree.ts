/**
 * 挑选树构建与勾选联动纯函数（18_挑选合并功能交互重设计.md §3.1-§3.2，INT-600）。
 * 联动规则 R1-R10 全部在此实现并单测；组件仅消费，不重算。
 * 依赖规则：domain 零依赖。
 */
import type {
  CartTreeBranch,
  CartTreeItem,
  CartTreeLeaf,
  CherryPickCandidate,
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
 * 挑选树构建（候选平铺行 → 四级分组 + 结果行叶）
 * ============================================================ */

/** 名称缺省降级（§11-2 + INT-713 打回 #1）：候选/条目未返名称时不裸显 36 位 UUID，改友好文案 + 截断 id */
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

/** §11-2 候选未返 result_type → result_type 级分组折叠为「结果类型待补充」 */
export const PENDING_RESULT_TYPE_KEY = '__pending__'
export const PENDING_RESULT_TYPE_LABEL = '结果类型待补充'

/** 设备/API 组 key（device_id 与 api_id 二选一，实测） */
function deviceKey(c: CherryPickCandidate): string {
  return c.deviceId != null ? `device:${c.deviceId}` : `api:${c.apiId ?? '?'}`
}

/** 候选行 result_type 分组 key（缺省折叠为待补充） */
function resultTypeKey(c: CherryPickCandidate): string {
  return c.resultType && c.resultType.trim() ? c.resultType : PENDING_RESULT_TYPE_KEY
}

function deviceName(c: CherryPickCandidate): string | null {
  return c.deviceName ?? c.apiName ?? null
}

/** 设备/API 级与 result_type 级 key 构造（任务视角与用例视角注入不同前缀防碰撞） */
interface DeviceLevelKeys {
  device: (dk: string) => string
  resultType: (dk: string, rt: string) => string
}

/** 结果行叶构造（§3.7.1 叶行口径；三视图共享，叶携带来源任务名消歧 §3.8.3） */
function buildLeafRows(
  rows: CherryPickCandidate[],
  addedResultIds: ReadonlySet<number>
): PickTreeLeaf[] {
  return rows.map((c) => ({
    kind: 'leaf',
    key: `leaf:${c.resultId}`,
    resultId: c.resultId,
    taskName: c.taskName,
    caseName: caseDisplayName(c.caseName, c.caseId),
    deviceName: c.deviceName,
    apiName: c.apiName,
    resultType: c.resultType,
    executionStatus: c.executionStatus,
    evaluationStatus: c.evaluationStatus,
    createdAt: c.createdAt,
    added: addedResultIds.has(c.resultId),
  }))
}

/**
 * 设备/result_type/任务/结果行叶 子树（用例视图用，§3.7.1 层级完整性：
 * 同一设备多个 result_type 各成独立并列分支，不压平为平铺叶）。
 * INT-1694 二次口径：result_type 之下是任务层（叶的前一级），任务数 ≤ 1 时省略。
 */
function buildDeviceBranches(
  rows: CherryPickCandidate[],
  addedResultIds: ReadonlySet<number>,
  keys: DeviceLevelKeys,
  omitTaskLayer: boolean
): PickTreeBranch[] {
  const deviceMap = new Map<string, CherryPickCandidate[]>()
  for (const c of rows) {
    const k = deviceKey(c)
    const list = deviceMap.get(k) ?? []
    list.push(c)
    deviceMap.set(k, list)
  }

  const devices: PickTreeBranch[] = []
  for (const [dk, deviceRows] of deviceMap) {
    const deviceDisplay = deviceGroupDisplayName(
      deviceName(deviceRows[0]),
      deviceRows[0]?.deviceId ?? null,
      deviceRows[0]?.apiId ?? null
    )
    const resultTypeMap = new Map<string, CherryPickCandidate[]>()
    for (const c of deviceRows) {
      const rt = resultTypeKey(c)
      const list = resultTypeMap.get(rt) ?? []
      list.push(c)
      resultTypeMap.set(rt, list)
    }

    const resultTypes: PickTreeBranch[] = []
    for (const [rt, rtRows] of resultTypeMap) {
      const rtKey = keys.resultType(dk, rt)
      resultTypes.push({
        kind: 'branch',
        key: rtKey,
        level: 'resultType',
        name: rt === PENDING_RESULT_TYPE_KEY ? PENDING_RESULT_TYPE_LABEL : rt,
        count: rtRows.length,
        resultIds: rtRows.map((c) => c.resultId),
        // A 组：result_type → 任务 → 结果行叶（任务在最末一级，叶的前一级）
        children: buildTaskLeafBranches(rtRows, addedResultIds, rtKey, omitTaskLayer),
      })
    }

    devices.push({
      kind: 'branch',
      key: keys.device(dk),
      level: 'device',
      name: deviceDisplay,
      count: deviceRows.length,
      resultIds: deviceRows.map((c) => c.resultId),
      children: resultTypes,
    })
  }
  return devices
}

/**
 * 平铺候选行 → 挑选树（任务→用例→被测设备/API→result_type→结果行叶）。
 * 叶携带 R10 已加购标记；树按白名单层级展开顺序稳定构造；用例节点携带
 * caseId（CaseIdBadge）与 algorithmType（算法徽章，§3.7.1）。
 */
export function buildPickTree(
  candidates: CherryPickCandidate[],
  addedResultIds: ReadonlySet<number> = new Set()
): PickTreeBranch[] {
  const taskMap = new Map<number, CherryPickCandidate[]>()

  for (const c of candidates) {
    const list = taskMap.get(c.taskId) ?? []
    list.push(c)
    taskMap.set(c.taskId, list)
  }

  const tasks: PickTreeBranch[] = []
  for (const [taskId, rows] of taskMap) {
    const taskName = rows[0]?.taskName ?? `任务 ${taskId}`
    const caseMap = new Map<string, CherryPickCandidate[]>()
    for (const c of rows) {
      const list = caseMap.get(c.caseId) ?? []
      list.push(c)
      caseMap.set(c.caseId, list)
    }

    const cases: PickTreeBranch[] = []
    for (const [caseId, caseRows] of caseMap) {
      const caseDisplay = caseDisplayName(caseRows[0]?.caseName, caseId)

      cases.push({
        kind: 'branch',
        key: `case:${taskId}:${caseId}`,
        level: 'case',
        name: caseDisplay,
        caseId,
        algorithmType: caseRows[0]?.algorithmType ?? null,
        ...caseMeta(caseRows),
        count: caseRows.length,
        resultIds: caseRows.map((c) => c.resultId),
        children: buildDeviceBranches(
          caseRows,
          addedResultIds,
          {
            device: (dk) => `device:${taskId}:${caseId}:${dk}`,
            resultType: (dk, rt) => `resultType:${taskId}:${caseId}:${dk}:${rt}`,
          },
          // 单任务树构建（buildPickTree）任务已在第一级，末端不再插任务层
          true
        ),
      })
    }

    tasks.push({
      kind: 'branch',
      key: `task:${taskId}`,
      level: 'task',
      name: taskName,
      count: rows.length,
      resultIds: rows.map((c) => c.resultId),
      children: cases,
    })
  }

  return tasks
}

/* ============================================================
 * 三视图树构建（负责人 2026-10-24 二次修正，INT-1694）：用例 / 设备 / 结果类型
 * 基础三视图（A 组）里**任务在最末一级（叶的前一级）**：任务之上的节点（组织层 /
 * 用例卡 / 设备·API / result_type）跨任务共享、不按 taskId 分簇、key 不带 taskId 命名空间；
 * 到任务层才按 taskId 分开，叶挂在该任务下。同一用例（或同一设备）在两个任务下都有结果时，
 * 上层节点只出现一次，最后按任务分成两个任务节点。
 * 阶段 2 只选 1 个任务时任务层恒定单值 → 该层自动省略不渲染（≥2 个任务才出现）。
 * 任务视图（B 组，仅购物车）任务在第一级，子树 key 带 taskId 命名空间。
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

/** A 组任务层省略判定：整棵树只有 1 个任务时该层恒定单值 */
function shouldOmitTaskLayer(taskIds: readonly number[]): boolean {
  return new Set(taskIds).size <= 1
}

/**
 * A 组末端任务层：rows 按 taskId 分簇 → 任务分支（level='task'，名取 taskName）→ 结果行叶。
 * 用例/设备/结果类型三视图的末端统一走它；omitTaskLayer=true 时直接返回叶（单任务场景）。
 */
export function buildTaskLeafBranches(
  rows: CherryPickCandidate[],
  addedResultIds: ReadonlySet<number>,
  keyPrefix: string,
  omitTaskLayer = false
): PickTreeItem[] {
  if (omitTaskLayer) return buildLeafRows(rows, addedResultIds)
  return groupRowsBySourceTask(
    rows,
    (c) => c.taskId,
    (c) => c.taskName
  ).map((cluster) => ({
    kind: 'branch' as const,
    key: `${keyPrefix}-task:${cluster.taskId}`,
    level: 'task' as const,
    name: cluster.taskName,
    count: cluster.rows.length,
    resultIds: cluster.rows.map((c) => c.resultId),
    children: buildLeafRows(cluster.rows, addedResultIds),
  }))
}

/** 用例级元信息（§11-7 真名：标签/分组/时长/轮次；同一用例跨候选行取值一致，取首行） */
function caseMeta(rows: CherryPickCandidate[]): {
  tags: string[]
  groupId: string | null
  groupName: string | null
  totalDuration: number | null
  rounds: number | null
} {
  const row = rows[0]
  return {
    tags: row?.tags ?? [],
    groupId: row?.groupId ?? null,
    groupName: row?.groupName ?? null,
    totalDuration: row?.totalDuration ?? null,
    rounds: row?.rounds ?? null,
  }
}

/** 用例级分支构造（三视图用例节点共用：名称 + CaseIdBadge + 算法徽章 + 计数，§3.8.3） */
function buildCaseNode(
  caseId: string,
  rows: CherryPickCandidate[],
  addedResultIds: ReadonlySet<number>,
  prefix: string,
  /** 用例下子层构造（三层视图各不相同，调用方按视图决定；caseKey 供任务层建 key） */
  buildChildren: (
    rows: CherryPickCandidate[],
    added: ReadonlySet<number>,
    caseKey: string
  ) => PickTreeItem[]
): PickTreeBranch {
  const key = `${prefix}:${caseId}`
  return {
    kind: 'branch',
    key,
    level: 'case',
    name: caseDisplayName(rows[0]?.caseName, caseId),
    caseId,
    algorithmType: rows[0]?.algorithmType ?? null,
    ...caseMeta(rows),
    count: rows.length,
    resultIds: rows.map((c) => c.resultId),
    children: buildChildren(rows, addedResultIds, key),
  }
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

/**
 * 用例视图（A 组，2026-10-24 二次口径）：用例层组织（组件按分组/标签聚合，INT-1694）
 * → 用例（用例管理卡）→ 设备/API → result_type → **任务** → 结果行。
 * 第 1 层组织在 UI 侧由 PickCaseOrgList 聚合，domain 只给用例平铺；
 * 用例/设备/result_type 层跨任务共享，任务层在最末一级。
 */export function buildPickCaseView(
  candidates: CherryPickCandidate[],
  addedResultIds: ReadonlySet<number> = new Set()
): PickTreeBranch[] {
  const omitTaskLayer = shouldOmitTaskLayer(candidates.map((c) => c.taskId))
  const caseMap = new Map<string, CherryPickCandidate[]>()
  for (const c of candidates) {
    const list = caseMap.get(c.caseId) ?? []
    list.push(c)
    caseMap.set(c.caseId, list)
  }

  const cases: PickTreeBranch[] = []
  for (const [caseId, caseRows] of caseMap) {
    cases.push(
      buildCaseNode(caseId, caseRows, addedResultIds, 'pcv', (r, added) =>
        buildDeviceBranches(
          r,
          added,
          {
            device: (dk) => `pcv-device:${caseId}:${dk}`,
            resultType: (dk, rt) => `pcv-resultType:${caseId}:${dk}:${rt}`,
          },
          omitTaskLayer
        )
      )
    )
  }

  return cases
}

/**
 * 设备视图（A 组）：设备/API → result_type → **用例层组织** → 用例 → 任务 → 结果行。
 * 组织层是独立一层（分组/标签组头），平铺子视图下用例卡直挂组头。
 */
export function buildPickDeviceView(
  candidates: CherryPickCandidate[],
  addedResultIds: ReadonlySet<number> = new Set(),
  org: PickCaseOrgDimension = 'group',
  subView: PickCaseOrgSubView = 'flat'
): PickTreeBranch[] {
  const omitTaskLayer = shouldOmitTaskLayer(candidates.map((c) => c.taskId))
  const deviceMap = new Map<string, CherryPickCandidate[]>()
  for (const c of candidates) {
    const k = deviceKey(c)
    const list = deviceMap.get(k) ?? []
    list.push(c)
    deviceMap.set(k, list)
  }

  const devices: PickTreeBranch[] = []
  for (const [dk, deviceRows] of deviceMap) {
    const deviceDisplay = deviceGroupDisplayName(
      deviceName(deviceRows[0]),
      deviceRows[0]?.deviceId ?? null,
      deviceRows[0]?.apiId ?? null
    )
    const resultTypeMap = new Map<string, CherryPickCandidate[]>()
    for (const c of deviceRows) {
      const rt = resultTypeKey(c)
      const list = resultTypeMap.get(rt) ?? []
      list.push(c)
      resultTypeMap.set(rt, list)
    }

    const resultTypes: PickTreeBranch[] = []
    for (const [rt, rtRows] of resultTypeMap) {
      const caseMap = new Map<string, CherryPickCandidate[]>()
      for (const c of rtRows) {
        const list = caseMap.get(c.caseId) ?? []
        list.push(c)
        caseMap.set(c.caseId, list)
      }
      const cases: PickTreeBranch[] = []
      for (const [caseId, caseRows] of caseMap) {
        cases.push(
          buildCaseNode(
            caseId,
            caseRows,
            addedResultIds,
            `dv-case:${dk}:${rt}`,
            (rows, added, caseKey) =>
              buildTaskLeafBranches(rows, added, caseKey, omitTaskLayer)
          )
        )
      }
      resultTypes.push({
        kind: 'branch',
        key: `dv-resultType:${dk}:${rt}`,
        level: 'resultType',
        name: rt === PENDING_RESULT_TYPE_KEY ? PENDING_RESULT_TYPE_LABEL : rt,
        count: rtRows.length,
        resultIds: rtRows.map((c) => c.resultId),
        // 组织层：result_type 之下、用例卡之上（分组/标签组头 → 用例卡）
        children: buildCaseOrgBranches(
          cases,
          org,
          subView,
          `dv-org:${dk}:${rt}`
        ),
      })
    }

    devices.push({
      kind: 'branch',
      key: `dv-device:${dk}`,
      level: 'device',
      name: deviceDisplay,
      count: deviceRows.length,
      resultIds: deviceRows.map((c) => c.resultId),
      children: resultTypes,
    })
  }

  return devices
}

/**
 * 结果类型视图（A 组）：result_type → 设备/API → **用例层组织** → 用例 → 任务 → 结果行。
 * 组织层位置与设备视图一致（result_type 之下的设备节点之后、用例卡之前）。
 */
export function buildPickResultTypeView(
  candidates: CherryPickCandidate[],
  addedResultIds: ReadonlySet<number> = new Set(),
  org: PickCaseOrgDimension = 'group',
  subView: PickCaseOrgSubView = 'flat'
): PickTreeBranch[] {
  const omitTaskLayer = shouldOmitTaskLayer(candidates.map((c) => c.taskId))
  const rtMap = new Map<string, CherryPickCandidate[]>()
  for (const c of candidates) {
    const rt = resultTypeKey(c)
    const list = rtMap.get(rt) ?? []
    list.push(c)
    rtMap.set(rt, list)
  }

  const resultTypes: PickTreeBranch[] = []
  for (const [rt, rtRows] of rtMap) {
    const deviceMap = new Map<string, CherryPickCandidate[]>()
    for (const c of rtRows) {
      const k = deviceKey(c)
      const list = deviceMap.get(k) ?? []
      list.push(c)
      deviceMap.set(k, list)
    }

    const devices: PickTreeBranch[] = []
    for (const [dk, deviceRows] of deviceMap) {
      const deviceDisplay = deviceGroupDisplayName(
        deviceName(deviceRows[0]),
        deviceRows[0]?.deviceId ?? null,
        deviceRows[0]?.apiId ?? null
      )
      const caseMap = new Map<string, CherryPickCandidate[]>()
      for (const c of deviceRows) {
        const list = caseMap.get(c.caseId) ?? []
        list.push(c)
        caseMap.set(c.caseId, list)
      }
      const cases: PickTreeBranch[] = []
      for (const [caseId, caseRows] of caseMap) {
        cases.push(
          buildCaseNode(
            caseId,
            caseRows,
            addedResultIds,
            `rtv-case:${rt}:${dk}`,
            (rows, added, caseKey) =>
              buildTaskLeafBranches(rows, added, caseKey, omitTaskLayer)
          )
        )
      }
      devices.push({
        kind: 'branch',
        key: `rtv-device:${rt}:${dk}`,
        level: 'device',
        name: deviceDisplay,
        count: deviceRows.length,
        resultIds: deviceRows.map((c) => c.resultId),
        // 组织层：设备/API 之下、用例卡之上（与设备视图同一层级语义）
        children: buildCaseOrgBranches(cases, org, subView, `rtv-org:${rt}:${dk}`),
      })
    }

    resultTypes.push({
      kind: 'branch',
      key: `rtv-resultType:${rt}`,
      level: 'resultType',
      name: rt === PENDING_RESULT_TYPE_KEY ? PENDING_RESULT_TYPE_LABEL : rt,
      count: rtRows.length,
      resultIds: rtRows.map((c) => c.resultId),
      children: devices,
    })
  }

  return resultTypes
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

/* ============================================================
 * 批量选择（R9：全选当前筛选/反选）
 * ============================================================ */

/** 收集当前树全部叶结果 id（当前筛选命中集） */
export function collectVisibleResultIds(
  items: PickTreeItem[]
): number[] {
  const ids: number[] = []
  for (const item of items) {
    if (item.kind === 'leaf') ids.push(item.resultId)
    else ids.push(...collectVisibleResultIds(item.children))
  }
  return ids
}

/** 全选当前筛选（跨页语义见 §11-4；当前树=已加载候选） */
export function selectAllVisible(
  items: PickTreeItem[],
  selectedIds: ReadonlySet<number>
): Set<number> {
  const next = new Set(selectedIds)
  for (const id of collectVisibleResultIds(items)) next.add(id)
  return next
}

/** 反选当前页可见节点（已选跨页项保留，§3.2 R9） */
export function invertVisibleSelection(
  items: PickTreeItem[],
  selectedIds: ReadonlySet<number>
): Set<number> {
  const next = new Set(selectedIds)
  for (const id of collectVisibleResultIds(items)) {
    if (next.has(id)) next.delete(id)
    else next.add(id)
  }
  return next
}

/** 清空选择 */
export function clearSelection(): Set<number> {
  return new Set()
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

/** 汇总条数据：结果条数 / 来源任务数 / 设备数 / 用例数（§9 文案「已选 {n} 条结果 · 来自 {m} 个任务 · 覆盖 {d} 台设备」） */
export function computeSelectionStats(
  items: PickTreeItem[],
  selectedIds: ReadonlySet<number>
): SelectionStats {
  const stats: SelectionStats = { results: 0, tasks: 0, devices: 0, cases: 0 }
  const taskSet = new Set<string>()
  const deviceSet = new Set<string>()
  const caseSet = new Set<string>()

  // 叶携带任务/用例/设备名（§3.8.3 三视图叶行消歧字段），按叶统计与视图无关——
  // 用例/设备/结果类型三视图对同一 selectedResultIds 统计口径一致。
  const walk = (nodes: PickTreeItem[]) => {
    for (const node of nodes) {
      if (node.kind === 'leaf') {
        if (!selectedIds.has(node.resultId)) continue
        stats.results += 1
        taskSet.add(node.taskName)
        caseSet.add(node.caseName)
        deviceSet.add(node.deviceName ?? node.apiName ?? '—')
      } else {
        walk(node.children)
      }
    }
  }
  walk(items)

  stats.tasks = taskSet.size
  stats.cases = caseSet.size
  stats.devices = deviceSet.size
  return stats
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

/** 用例视图形状：用例 → 设备/API → result_type → (任务层 | 叶) */
function cartCaseViewNodes(
  entries: PickCartEntry[],
  keyPrefix: string,
  taskLayer: boolean,
  omitTaskLayer: boolean
): CartTreeBranch[] {
  const cases: CartTreeBranch[] = []
  for (const caseRows of groupEntries(entries, cartCaseKey).values()) {
    cases.push(
      buildCartCaseNode(caseRows, keyPrefix, (rows, caseKey) => {
        const devices: CartTreeItem[] = []
        for (const deviceRows of groupEntries(rows, cartDeviceKey).values()) {
          devices.push(
            buildCartDeviceNode(deviceRows, caseKey, (dRows, deviceKey) => {
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
 */
function cartDeviceViewNodes(
  entries: PickCartEntry[],
  keyPrefix: string,
  taskLayer: boolean,
  omitTaskLayer: boolean,
  org: PickCaseOrgDimension = 'group',
  subView: PickCaseOrgSubView = 'flat'
): CartTreeBranch[] {
  const devices: CartTreeBranch[] = []
  for (const deviceRows of groupEntries(entries, cartDeviceKey).values()) {
    devices.push(
      buildCartDeviceNode(deviceRows, keyPrefix, (rows, deviceKey) => {
        const resultTypes: CartTreeItem[] = []
        for (const rtRows of groupEntries(rows, cartResultTypeKey).values()) {
          resultTypes.push(
            buildCartResultTypeNode(rtRows, deviceKey, (rtRowList, rtKey) => {
              const cases: CartTreeBranch[] = []
              for (const caseRows of groupEntries(rtRowList, cartCaseKey).values()) {
                cases.push(
                  buildCartCaseNode(caseRows, rtKey, (leafRows, caseKey) =>
                    cartLeafLayer(leafRows, caseKey, taskLayer, omitTaskLayer)
                  )
                )
              }
              // 组织层：result_type 之下、用例卡之上
              return cartCaseOrgLevel(cases, org, subView, rtKey)
            })
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
 * 购物车 / 复核抽屉恒显任务层（单任务也不省略，与阶段 2 单任务省略口径相反）。
 */
export function buildCartCaseView(groups: PickCartGroup[]): CartTreeBranch[] {
  return cartCaseViewNodes(cartEntriesOf(groups), 'cv', true, false)
}

/** 购物车设备视图（A 组）：设备/API → result_type → 组织层 → 用例（PickCaseCard）→ 任务 → 叶 */
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
    subView
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
    const children: CartTreeItem[] =
      subView === 'case'
        ? cartCaseViewNodes(group.entries, keyPrefix, false, false)
        : subView === 'device'
          ? cartDeviceViewNodes(group.entries, keyPrefix, false, false, org, caseOrgSubView)
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
  for (const item of items) {
    if (item.kind === 'leaf') ids.push(item.entryId)
    else ids.push(...collectEntryIds(item.children))
  }
  return ids
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

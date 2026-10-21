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
  PickLevel,
  PickTreeBranch,
  PickTreeItem,
  PickTreeLeaf,
  SelectionState,
} from '@/domain/models/cherryPick'

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
 * 设备/result_type/结果行叶 三级子树（任务视角与用例视角共用，§3.7.1 层级完整性：
 * 同一设备多个 result_type 各成独立并列分支，不压平为平铺叶）。
 */
function buildDeviceBranches(
  rows: CherryPickCandidate[],
  addedResultIds: ReadonlySet<number>,
  keys: DeviceLevelKeys
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
      const leaves = buildLeafRows(rtRows, addedResultIds)
      resultTypes.push({
        kind: 'branch',
        key: keys.resultType(dk, rt),
        level: 'resultType',
        name: rt === PENDING_RESULT_TYPE_KEY ? PENDING_RESULT_TYPE_LABEL : rt,
        count: leaves.length,
        resultIds: rtRows.map((c) => c.resultId),
        children: leaves,
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
        count: caseRows.length,
        resultIds: caseRows.map((c) => c.resultId),
        children: buildDeviceBranches(caseRows, addedResultIds, {
          device: (dk) => `device:${taskId}:${caseId}:${dk}`,
          resultType: (dk, rt) => `resultType:${taskId}:${caseId}:${dk}:${rt}`,
        }),
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
 * 三视图树构建（§3.8.3 裁定③，INT-1047）：用例 / 设备 / 结果类型
 * 任务维度由阶段 1 承载（§3.8.2），三视图树内不再设任务级分支；
 * 叶结果行携带 taskName 消歧（同一叶在任务 A/B 各出现一次，按 result_id 独立勾选）。
 * ============================================================ */

/** 用例级分支构造（三视图用例节点共用：名称 + CaseIdBadge + 算法徽章 + 计数，§3.8.3） */
function buildCaseNode(
  caseId: string,
  rows: CherryPickCandidate[],
  addedResultIds: ReadonlySet<number>,
  prefix: string,
  /** 用例下子层构造（用例视图=device→result_type→叶；设备/结果类型视图=叶直挂） */
  buildChildren: (rows: CherryPickCandidate[], added: ReadonlySet<number>) => PickTreeItem[]
): PickTreeBranch {
  return {
    kind: 'branch',
    key: `${prefix}:${caseId}`,
    level: 'case',
    name: caseDisplayName(rows[0]?.caseName, caseId),
    caseId,
    algorithmType: rows[0]?.algorithmType ?? null,
    count: rows.length,
    resultIds: rows.map((c) => c.resultId),
    children: buildChildren(rows, addedResultIds),
  }
}

/** 用例视图（§3.8.3）：用例（用例管理卡）→ 设备/API → result_type → 结果行 */
export function buildPickCaseView(
  candidates: CherryPickCandidate[],
  addedResultIds: ReadonlySet<number> = new Set()
): PickTreeBranch[] {
  const caseMap = new Map<string, CherryPickCandidate[]>()
  for (const c of candidates) {
    const list = caseMap.get(c.caseId) ?? []
    list.push(c)
    caseMap.set(c.caseId, list)
  }

  const cases: PickTreeBranch[] = []
  for (const [caseId, caseRows] of caseMap) {
    cases.push(
      buildCaseNode(caseId, caseRows, addedResultIds, 'pcase', (rows, added) =>
        buildDeviceBranches(rows, added, {
          device: (dk) => `pcase-device:${caseId}:${dk}`,
          resultType: (dk, rt) => `pcase-resultType:${caseId}:${dk}:${rt}`,
        })
      )
    )
  }

  return cases
}

/** 设备视图（§3.8.3）：设备/API → result_type → 用例 → 结果行（设备/结果类型视图用例级叶直挂） */
export function buildPickDeviceView(
  candidates: CherryPickCandidate[],
  addedResultIds: ReadonlySet<number> = new Set()
): PickTreeBranch[] {
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
          buildCaseNode(caseId, caseRows, addedResultIds, `dv-case:${dk}:${rt}`, (rows, added) =>
            buildLeafRows(rows, added)
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
        children: cases,
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

/** 结果类型视图（§3.8.3）：result_type → 设备/API → 用例 → 结果行 */
export function buildPickResultTypeView(
  candidates: CherryPickCandidate[],
  addedResultIds: ReadonlySet<number> = new Set()
): PickTreeBranch[] {
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
          buildCaseNode(caseId, caseRows, addedResultIds, `rtv-case:${rt}:${dk}`, (rows, added) =>
            buildLeafRows(rows, added)
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
        children: cases,
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
 * 购物车树构建（§4.2：任务→用例→设备→result_type，同构挑选树）
 * result_type 级分组受 §11-5 限制：条目快照无 source_result_type 时折叠缺省
 * ============================================================ */

export function buildCartTree(groups: { taskId: number; taskName: string; entries: PickCartEntry[] }[]): CartTreeBranch[] {
  return groups.map((group) => {
    const caseMap = new Map<string, PickCartEntry[]>()
    for (const e of group.entries) {
      const key = e.sourceCaseId ?? 'unknown'
      const list = caseMap.get(key) ?? []
      list.push(e)
      caseMap.set(key, list)
    }

    const cases: CartTreeBranch[] = []
    for (const [caseKey, caseRows] of caseMap) {
      const caseName = caseDisplayName(
        caseRows[0]?.sourceCaseName,
        caseRows[0]?.sourceCaseId ?? null
      )
      const deviceMap = new Map<string, PickCartEntry[]>()
      for (const e of caseRows) {
        const key = e.sourceDeviceId != null ? `device:${e.sourceDeviceId}` : `api:${e.sourceApiId ?? '?'}`
        const list = deviceMap.get(key) ?? []
        list.push(e)
        deviceMap.set(key, list)
      }

      const devices: CartTreeBranch[] = []
      for (const [dk, deviceRows] of deviceMap) {
        const deviceDisplay = deviceGroupDisplayName(
          deviceRows[0]?.sourceDeviceName ?? deviceRows[0]?.sourceApiName ?? null,
          deviceRows[0]?.sourceDeviceId ?? null,
          deviceRows[0]?.sourceApiId ?? null
        )
        // §3.7.2/§11-5：source_result_type 落地后完整重建 result_type 级——
        // 同一设备下多个 result_type 各成独立分支可独立展开/收起；历史快照
        // 缺 source_result_type 的条目折叠为「结果类型待补充」单组。
        const resultTypeMap = new Map<string, PickCartEntry[]>()
        for (const e of deviceRows) {
          const rt =
            e.sourceResultType && e.sourceResultType.trim()
              ? e.sourceResultType
              : PENDING_RESULT_TYPE_KEY
          const list = resultTypeMap.get(rt) ?? []
          list.push(e)
          resultTypeMap.set(rt, list)
        }

        const resultTypes: CartTreeBranch[] = []
        for (const [rt, rtRows] of resultTypeMap) {
          const leaves: CartTreeLeaf[] = rtRows.map((e) => ({
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
          }))
          resultTypes.push({
            kind: 'branch',
            key: `cart-resultType:${group.taskId}:${caseKey}:${dk}:${rt}`,
            level: 'resultType',
            name: rt === PENDING_RESULT_TYPE_KEY ? PENDING_RESULT_TYPE_LABEL : rt,
            count: leaves.length,
            entryIds: rtRows.map((e) => e.itemId),
            children: leaves,
          })
        }
        devices.push({
          kind: 'branch',
          key: `cart-device:${group.taskId}:${caseKey}:${dk}`,
          level: 'device',
          name: deviceDisplay,
          count: deviceRows.length,
          entryIds: deviceRows.map((e) => e.itemId),
          children: resultTypes,
        })
      }

      cases.push({
        kind: 'branch',
        key: `cart-case:${group.taskId}:${caseKey}`,
        level: 'case',
        name: caseName,
        caseId: caseRows[0]?.sourceCaseId ?? undefined,
        count: caseRows.length,
        entryIds: caseRows.map((e) => e.itemId),
        children: devices,
      })
    }

    return {
      kind: 'branch',
      key: `cart-task:${group.taskId}`,
      level: 'task',
      name: group.taskName,
      count: group.entries.length,
      entryIds: group.entries.map((e) => e.itemId),
      children: cases,
    }
  })
}

/* ============================================================
 * 购物车三视图树构建（§4.2 ②，INT-1128）：用例 / 设备 / 结果类型
 * 购物车条目快照（source_task/case/device/api/result_type）重建三棵聚合树，
 * 与挑选页同层级口径（树内不设任务级分支）；任务维度以 叶行来源任务名 +
 * 顶层组头「来自 {m} 个任务」保留（§4.2 ②-①/②-②）。纯函数，组件仅消费。
 * ============================================================ */

/** 购物车条目 → case 分组 key（缺失折叠 unknown，与 buildCartTree 同口径） */
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

/** 购物车叶行构造（来源任务名消歧字段 §4.2 ②-①） */
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

/** 设备/API 级分支构造（购物车三视图共用：设备 → result_type → 叶） */
function buildCartDeviceBranch(
  entries: PickCartEntry[],
  prefix: string
): CartTreeBranch {
  const dk = cartDeviceKey(entries[0])
  const deviceDisplay = deviceGroupDisplayName(
    entries[0]?.sourceDeviceName ?? entries[0]?.sourceApiName ?? null,
    entries[0]?.sourceDeviceId ?? null,
    entries[0]?.sourceApiId ?? null
  )
  const resultTypeMap = new Map<string, PickCartEntry[]>()
  for (const e of entries) {
    const rt = cartResultTypeKey(e)
    const list = resultTypeMap.get(rt) ?? []
    list.push(e)
    resultTypeMap.set(rt, list)
  }

  const resultTypes: CartTreeBranch[] = []
  for (const [rt, rtRows] of resultTypeMap) {
    const leaves = rtRows.map(buildCartLeaf)
    resultTypes.push({
      kind: 'branch',
      key: `${prefix}-resultType:${dk}:${rt}`,
      level: 'resultType',
      name: rt === PENDING_RESULT_TYPE_KEY ? PENDING_RESULT_TYPE_LABEL : rt,
      count: leaves.length,
      entryIds: rtRows.map((e) => e.itemId),
      children: leaves,
    })
  }

  return {
    kind: 'branch',
    key: `${prefix}-device:${dk}`,
    level: 'device',
    name: deviceDisplay,
    count: entries.length,
    entryIds: entries.map((e) => e.itemId),
    children: resultTypes,
  }
}

/** 用例级分支构造（购物车用例节点 = PickCaseCard，§3.8.4） */
function buildCartCaseBranch(
  entries: PickCartEntry[],
  prefix: string,
  buildChildren: (entries: PickCartEntry[]) => CartTreeItem[]
): CartTreeBranch {
  const first = entries[0]
  return {
    kind: 'branch',
    key: `${prefix}-case:${cartCaseKey(first)}`,
    level: 'case',
    name: caseDisplayName(first?.sourceCaseName, first?.sourceCaseId ?? null),
    caseId: first?.sourceCaseId ?? undefined,
    count: entries.length,
    entryIds: entries.map((e) => e.itemId),
    children: buildChildren(entries),
  }
}

/** 购物车用例视图（§4.2 ②）：用例（PickCaseCard）→ 设备/API → result_type → 叶 */
export function buildCartCaseView(groups: PickCartGroup[]): CartTreeBranch[] {
  const caseMap = new Map<string, PickCartEntry[]>()
  for (const g of groups) {
    for (const e of g.entries) {
      const ck = cartCaseKey(e)
      const list = caseMap.get(ck) ?? []
      list.push(e)
      caseMap.set(ck, list)
    }
  }

  const cases: CartTreeBranch[] = []
  for (const [ck, caseRows] of caseMap) {
    const deviceMap = new Map<string, PickCartEntry[]>()
    for (const e of caseRows) {
      const dk = cartDeviceKey(e)
      const list = deviceMap.get(dk) ?? []
      list.push(e)
      deviceMap.set(dk, list)
    }
    const devices: CartTreeBranch[] = []
    for (const deviceRows of deviceMap.values()) {
      devices.push(buildCartDeviceBranch(deviceRows, `cv-${ck}`))
    }
    cases.push(buildCartCaseBranch(caseRows, 'cv', () => devices))
  }

  return cases
}

/** 购物车设备视图（§4.2 ②）：设备/API → result_type → 用例（PickCaseCard）→ 叶 */
export function buildCartDeviceView(groups: PickCartGroup[]): CartTreeBranch[] {
  const deviceMap = new Map<string, PickCartEntry[]>()
  for (const g of groups) {
    for (const e of g.entries) {
      const dk = cartDeviceKey(e)
      const list = deviceMap.get(dk) ?? []
      list.push(e)
      deviceMap.set(dk, list)
    }
  }

  const devices: CartTreeBranch[] = []
  for (const [dk, deviceRows] of deviceMap) {
    const deviceDisplay = deviceGroupDisplayName(
      deviceRows[0]?.sourceDeviceName ?? deviceRows[0]?.sourceApiName ?? null,
      deviceRows[0]?.sourceDeviceId ?? null,
      deviceRows[0]?.sourceApiId ?? null
    )
    const resultTypeMap = new Map<string, PickCartEntry[]>()
    for (const e of deviceRows) {
      const rt = cartResultTypeKey(e)
      const list = resultTypeMap.get(rt) ?? []
      list.push(e)
      resultTypeMap.set(rt, list)
    }

    const resultTypes: CartTreeBranch[] = []
    for (const [rt, rtRows] of resultTypeMap) {
      const caseMap = new Map<string, PickCartEntry[]>()
      for (const e of rtRows) {
        const ck = cartCaseKey(e)
        const list = caseMap.get(ck) ?? []
        list.push(e)
        caseMap.set(ck, list)
      }
      const cases: CartTreeBranch[] = []
      for (const caseRows of caseMap.values()) {
        cases.push(
          buildCartCaseBranch(caseRows, `dv-${dk}-${rt}`, (rows) =>
            rows.map(buildCartLeaf)
          )
        )
      }
      resultTypes.push({
        kind: 'branch',
        key: `dv-resultType:${dk}:${rt}`,
        level: 'resultType',
        name: rt === PENDING_RESULT_TYPE_KEY ? PENDING_RESULT_TYPE_LABEL : rt,
        count: rtRows.length,
        entryIds: rtRows.map((e) => e.itemId),
        children: cases,
      })
    }

    devices.push({
      kind: 'branch',
      key: `dv-device:${dk}`,
      level: 'device',
      name: deviceDisplay,
      count: deviceRows.length,
      entryIds: deviceRows.map((e) => e.itemId),
      children: resultTypes,
    })
  }

  return devices
}

/** 购物车结果类型视图（§4.2 ②）：result_type → 设备/API → 用例（PickCaseCard）→ 叶 */
export function buildCartResultTypeView(groups: PickCartGroup[]): CartTreeBranch[] {
  const rtMap = new Map<string, PickCartEntry[]>()
  for (const g of groups) {
    for (const e of g.entries) {
      const rt = cartResultTypeKey(e)
      const list = rtMap.get(rt) ?? []
      list.push(e)
      rtMap.set(rt, list)
    }
  }

  const resultTypes: CartTreeBranch[] = []
  for (const [rt, rtRows] of rtMap) {
    const deviceMap = new Map<string, PickCartEntry[]>()
    for (const e of rtRows) {
      const dk = cartDeviceKey(e)
      const list = deviceMap.get(dk) ?? []
      list.push(e)
      deviceMap.set(dk, list)
    }

    const devices: CartTreeBranch[] = []
    for (const [dk, deviceRows] of deviceMap) {
      const deviceDisplay = deviceGroupDisplayName(
        deviceRows[0]?.sourceDeviceName ?? deviceRows[0]?.sourceApiName ?? null,
        deviceRows[0]?.sourceDeviceId ?? null,
        deviceRows[0]?.sourceApiId ?? null
      )
      const caseMap = new Map<string, PickCartEntry[]>()
      for (const e of deviceRows) {
        const ck = cartCaseKey(e)
        const list = caseMap.get(ck) ?? []
        list.push(e)
        caseMap.set(ck, list)
      }
      const cases: CartTreeBranch[] = []
      for (const caseRows of caseMap.values()) {
        cases.push(
          buildCartCaseBranch(caseRows, `rtv-${rt}-${dk}`, (rows) =>
            rows.map(buildCartLeaf)
          )
        )
      }
      devices.push({
        kind: 'branch',
        key: `rtv-device:${rt}:${dk}`,
        level: 'device',
        name: deviceDisplay,
        count: deviceRows.length,
        entryIds: deviceRows.map((e) => e.itemId),
        children: cases,
      })
    }

    resultTypes.push({
      kind: 'branch',
      key: `rtv-resultType:${rt}`,
      level: 'resultType',
      name: rt === PENDING_RESULT_TYPE_KEY ? PENDING_RESULT_TYPE_LABEL : rt,
      count: rtRows.length,
      entryIds: rtRows.map((e) => e.itemId),
      children: devices,
    })
  }

  return resultTypes
}

/** 收集节点内去重来源任务数（三视图顶层组头「来自 {m} 个任务」/移除整组确认文案，§4.2 ②-②） */
export function collectSourceTaskCount(items: CartTreeItem[]): number {
  const taskIds = new Set<number>()
  const walk = (nodes: CartTreeItem[]) => {
    for (const node of nodes) {
      if (node.kind === 'leaf') taskIds.add(node.sourceTaskId)
      else walk(node.children)
    }
  }
  walk(items)
  return taskIds.size
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
}

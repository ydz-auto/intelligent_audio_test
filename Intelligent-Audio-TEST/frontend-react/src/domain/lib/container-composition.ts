/**
 * 合并容器（挑选合并）组成区纯函数（18_挑选合并功能交互重设计.md §5.5.3/§5.5.4/§5.5.8，INT-1711）。
 * source 端点实测只到 id 级（无 case_name / device_name / api_name / result_type /
 * 结果级执行·评估状态，§11-8 FEAT 待补），故用容器详情 `cases[] / devices[] / apis[]`
 * 按 `source_case_id / source_device_id / source_api_id` join 出具名条目；
 * 条目形状与购物车 `PickCartEntry` 同构，故三视图直接复用
 * `buildCartCaseView` / `buildCartDeviceView` / `buildCartResultTypeView`，
 * 任务视图走 `CartTree view='task'`——不另造一套树、不新增端点。
 * §11-8 落地后 `results[]` 自带结果级字段，本文件取真实值、join 自动退化为兜底，树结构不变。
 * 依赖规则：domain 零依赖（只 import domain/models 与 domain/lib）。
 */
import type {
  ContainerSourceResult,
  ContainerSourceTrace,
  PickCartEntry,
  PickCartGroup,
} from '@/domain/models/cherryPick'
import type {
  TaskApiBrief,
  TaskCaseBrief,
  TaskDeviceBrief,
} from '@/domain/models/task'
import {
  groupCasesByCaseGroup,
  groupCasesByTag,
  type SubViewCaseItem,
} from '@/domain/lib/sub-view-aggregation'

/** 组成条目（与 PickCartEntry 同形 + 容器叶行展示所需字段） */
export interface CompositionEntry extends PickCartEntry {
  /** 源结果创建时间（§11-8 的 result_created_at；未落地 → null，叶行时间位不渲染） */
  resultCreatedAt: string | null
  /** 结果级已评估（§11-8 未落地 → 降级取容器用例行评估状态） */
  evaluated: boolean
  /** 执行状态是否来自降级（同 source_case_id 的容器用例行，工具行一次性提示用） */
  statusFromCase: boolean
  /** 评估状态是否来自降级（同 source_case_id 的容器用例行，工具行一次性提示用） */
  evaluationFromCase: boolean
  /** 用例分组名（详情 cases[].group_name，用例层组织数据源） */
  sourceCaseGroupName: string | null
  /** 用例标签（详情 cases[].tags，用例层组织数据源） */
  sourceCaseTags: string[]
}

/** 组成摘要（§5.5.8 summarizeComposition） */
export interface CompositionSummary {
  /** 结果条数（source.total / 条目数） */
  total: number
  /** 执行失败条数 */
  failed: number
  /** 未评估条数 */
  unevaluated: number
  /** 失效条数（results[].missing） */
  missing: number
  /** 来源任务数 */
  taskCount: number
  /** 用例数（去重 source_case_id） */
  caseCount: number
  /** 设备数（去重 source_device_id / source_api_id） */
  deviceCount: number
}

/** 执行状态筛选（§5.5.4 筛选联动，纯客户端） */
export type CompositionExecutionFilter = 'all' | 'completed' | 'failed' | 'stopped'
/** 评估状态筛选（§5.5.4 筛选联动，纯客户端） */
export type CompositionEvaluationFilter = 'all' | 'evaluated' | 'unevaluated'

/** 条目 id 前缀（不同源结果的 result_id 即可唯一，前缀便于叶行反查） */
const ENTRY_PREFIX = 'result:'

/** 组成条目 id（CartTree 叶行 key / entryId） */
export function compositionEntryId(resultId: number): string {
  return `${ENTRY_PREFIX}${resultId}`
}

/** 容器用例行索引（降级状态数据源，§5.5.4） */
function indexCases(cases: TaskCaseBrief[]): Map<string, TaskCaseBrief> {
  const map = new Map<string, TaskCaseBrief>()
  for (const c of cases) map.set(c.case_id, c)
  return map
}

/** 一条源结果 → 组成条目（§11-8 未落地：状态 / 评估 / 名 / 类型按 §5.5.4 降级口径） */
function toCompositionEntry(
  result: ContainerSourceResult,
  group: { sourceTaskId: number; sourceTaskName: string | null },
  cases: Map<string, TaskCaseBrief>,
  devices: Map<number, TaskDeviceBrief>,
  apis: Map<number, TaskApiBrief>
): CompositionEntry {
  const caseRow = result.sourceCaseId ? cases.get(result.sourceCaseId) ?? null : null
  const deviceRow =
    result.sourceDeviceId != null ? devices.get(result.sourceDeviceId) ?? null : null
  const apiRow = result.sourceApiId != null ? apis.get(result.sourceApiId) ?? null : null

  // §5.5.4 降级口径：结果级状态未返 → 取同 source_case_id 的容器用例行状态
  const statusFromCase = result.executionStatus == null
  const executionStatus =
    result.executionStatus ?? caseRow?.execution_status ?? 'unknown'

  // 评估侧同口径：结果级 evaluated 未返 → 容器用例行 evaluation_status === completed
  const evaluationFromCase = result.evaluated == null
  const evaluated =
    result.evaluated ?? (caseRow?.evaluation_status === 'completed')
  const evaluationStatus = evaluated
    ? 'completed'
    : caseRow?.evaluation_status ?? 'pending'

  return {
    itemId: compositionEntryId(result.resultId),
    resultId: result.resultId,
    sourceTaskId: group.sourceTaskId,
    sourceTaskName: group.sourceTaskName ?? `任务 ${group.sourceTaskId}`,
    sourceCaseId: result.sourceCaseId,
    sourceCaseName: result.caseName ?? caseRow?.name ?? null,
    sourceDeviceId: result.sourceDeviceId,
    sourceDeviceName: result.deviceName ?? deviceRow?.name ?? null,
    sourceApiId: result.sourceApiId,
    sourceApiName: result.apiName ?? apiRow?.name ?? null,
    // §11-8 未落地 → null，result_type 级分组折叠「结果类型待补充」
    sourceResultType: result.resultType,
    executionStatus,
    evaluationStatus,
    invalid: result.missing,
    resultCreatedAt: result.resultCreatedAt,
    evaluated,
    statusFromCase,
    evaluationFromCase,
    sourceCaseGroupName: caseRow?.group_name ?? null,
    sourceCaseTags: caseRow?.tags ?? [],
  }
}

/**
 * 容器溯源 + 容器详情 → 组成条目（§5.5.3 数据装配，与购物车 PickCartEntry 同构）。
 * 名 / 分组 / 标签由详情 join；缺名保持 null，由 CartTree 降级为「用例不可用 {前 8 位}…」等文案。
 */
export function toCompositionEntries(
  trace: ContainerSourceTrace | null,
  cases: TaskCaseBrief[] = [],
  devices: TaskDeviceBrief[] = [],
  apis: TaskApiBrief[] = []
): CompositionEntry[] {
  if (!trace) return []
  const caseMap = indexCases(cases)
  const deviceMap = new Map(devices.map((d) => [d.id, d]))
  const apiMap = new Map(apis.map((a) => [a.id, a]))
  const entries: CompositionEntry[] = []
  for (const group of trace.groups) {
    for (const result of group.results) {
      entries.push(toCompositionEntry(result, group, caseMap, deviceMap, apiMap))
    }
  }
  return entries
}

/** 组成条目 → 按来源任务分组（购物车同构，CartTree / 三视图纯函数入参） */
export function groupCompositionEntries(
  entries: CompositionEntry[]
): PickCartGroup[] {
  const groups = new Map<number, PickCartGroup>()
  for (const e of entries) {
    const existing = groups.get(e.sourceTaskId)
    if (existing) {
      existing.entries.push(e)
    } else {
      groups.set(e.sourceTaskId, {
        taskId: e.sourceTaskId,
        taskName: e.sourceTaskName,
        entries: [e],
      })
    }
  }
  return [...groups.values()]
}

/**
 * 组成摘要（§5.5.8）：条数 / 失败 / 未评估 / 失效 / 任务数 / 用例数 / 设备数。
 * 与 §5.5.4 分支计数同口径——入参为「过滤后」条目时即按命中集重算。
 */
export function summarizeComposition(
  entries: CompositionEntry[]
): CompositionSummary {
  const taskIds = new Set<number>()
  const caseIds = new Set<string>()
  const deviceKeys = new Set<string>()
  let failed = 0
  let unevaluated = 0
  let missing = 0

  for (const e of entries) {
    taskIds.add(e.sourceTaskId)
    if (e.sourceCaseId) caseIds.add(e.sourceCaseId)
    if (e.sourceDeviceId != null) deviceKeys.add(`device:${e.sourceDeviceId}`)
    else if (e.sourceApiId != null) deviceKeys.add(`api:${e.sourceApiId}`)
    if (e.executionStatus === 'failed') failed += 1
    if (!e.evaluated) unevaluated += 1
    if (e.invalid) missing += 1
  }

  return {
    total: entries.length,
    failed,
    unevaluated,
    missing,
    taskCount: taskIds.size,
    caseCount: caseIds.size,
    deviceCount: deviceKeys.size,
  }
}

/** 筛选命中判定（§5.5.4：执行状态 / 评估状态 facet） */
export function matchesCompositionFilter(
  entry: CompositionEntry,
  execution: CompositionExecutionFilter,
  evaluation: CompositionEvaluationFilter
): boolean {
  if (execution !== 'all' && entry.executionStatus !== execution) return false
  if (evaluation === 'evaluated' && !entry.evaluated) return false
  if (evaluation === 'unevaluated' && entry.evaluated) return false
  return true
}

/**
 * 纯客户端筛选组成树（§5.5.4）：命中叶保留，祖先由重建自然保留、分支计数按命中集重算；
 * 不改变层级结构与展开态（展开态由 CartTree 会话态保持）。
 */
export function filterCompositionEntries(
  entries: CompositionEntry[],
  execution: CompositionExecutionFilter = 'all',
  evaluation: CompositionEvaluationFilter = 'all'
): CompositionEntry[] {
  return entries.filter((e) => matchesCompositionFilter(e, execution, evaluation))
}

/** 只看失效（§5.5.6 Alert 操作） */
export function filterMissingEntries(
  entries: CompositionEntry[]
): CompositionEntry[] {
  return entries.filter((e) => e.invalid)
}

/* ============================================================
 * 用例层组织（§3.8.3 / §5.5.3：数据源 = 详情 cases[].group_name / tags）
 * ============================================================ */

/** 组织单元（一个用例 + 它的组成条目） */
export interface CompositionCaseUnit extends SubViewCaseItem {
  key: string
  caseId: string | null
  caseName: string
  entries: CompositionEntry[]
}

/** 组织分组（一层；交叉子视图时 subGroups 非空） */
export interface CompositionCaseOrgGroup {
  key: string
  label: string
  color: string | null
  categoryName: string | null
  units: CompositionCaseUnit[]
  subGroups: CompositionCaseOrgGroup[]
}

/** 条目 → 用例单元（按 source_case_id 聚合；缺失 case id 落 unknown 桶） */
export function buildCompositionCaseUnits(
  entries: CompositionEntry[]
): CompositionCaseUnit[] {
  const units = new Map<string, CompositionCaseUnit>()
  for (const e of entries) {
    const key = e.sourceCaseId ?? 'unknown'
    const existing = units.get(key)
    if (existing) {
      existing.entries.push(e)
      continue
    }
    units.set(key, {
      key,
      caseId: e.sourceCaseId,
      caseName: e.sourceCaseName ?? e.sourceCaseId ?? '未知用例',
      tags: e.sourceCaseTags,
      // 容器详情只有 group_name、无 group_id → 以组名作稳定分组键
      groupId: e.sourceCaseGroupName,
      groupName: e.sourceCaseGroupName,
      totalDuration: null,
      entries: [e],
    })
  }
  return [...units.values()]
}

/** 组织子分组 → 展示分组（透传标签色/分类角标） */
function toOrgGroup(
  group: {
    key: string
    label: string
    cases: CompositionCaseUnit[]
    color: string | null
    categoryName: string | null
  }
): CompositionCaseOrgGroup {
  return {
    key: group.key,
    label: group.label,
    color: group.color,
    categoryName: group.categoryName,
    units: group.cases,
    subGroups: [],
  }
}

/**
 * 用例层组织（分组视图 / 标签视图 × 平铺 / 交叉）。
 * 平铺 = 一层组织；交叉 = 一层组织内再按另一维度分子组（分组视图内按标签 / 标签视图内按分组）。
 */
export function organizeCompositionCases(
  entries: CompositionEntry[],
  org: 'group' | 'tag',
  subView: 'flat' | 'byTag' | 'byGroup'
): CompositionCaseOrgGroup[] {
  const units = buildCompositionCaseUnits(entries)
  const primary =
    org === 'group'
      ? groupCasesByCaseGroup(units)
      : groupCasesByTag(units, [])
  const result = primary.map(toOrgGroup)
  if (subView === 'flat') return result

  // 交叉子视图：换另一维度再分子组（空组不下发）
  const secondaryOrg = org === 'group' ? 'tag' : 'group'
  return result.map((group) => ({
    ...group,
    subGroups: (secondaryOrg === 'tag'
      ? groupCasesByTag(group.units, [])
      : groupCasesByCaseGroup(group.units)
    ).map(toOrgGroup),
  }))
}

/** 组织分组内全部条目（扁平化，供 CartTree 入参） */
export function orgGroupEntries(group: CompositionCaseOrgGroup): CompositionEntry[] {
  return group.units.flatMap((u) => u.entries)
}

/* ============================================================
 * 列表执行状态映射（§5.5.4：混态显示「部分失败」，纯前端展示映射，不改契约）
 * ============================================================ */

/**
 * 容器执行状态混态判定（§5.5.4 列表执行状态列 / §5.5.2 ①）：
 * - `partial`：0 < failed_cases < case_count → 「部分失败」（warning）
 * - `all`：failed_cases = case_count（且 > 0）→ 「已失败」（沿用后端 failed 映射）
 * - `none`：failed_cases = 0 或计数缺失 → 不映射，沿用原执行状态徽章
 * 后端字符串仍为 `failed`，这里只决定展示口径。
 */
export type ContainerMixState = 'none' | 'partial' | 'all'

export function containerMixState(
  failedCases: number | null | undefined,
  caseCount: number | null | undefined
): ContainerMixState {
  if (failedCases == null || caseCount == null) return 'none'
  if (caseCount <= 0 || failedCases <= 0) return 'none'
  return failedCases >= caseCount ? 'all' : 'partial'
}

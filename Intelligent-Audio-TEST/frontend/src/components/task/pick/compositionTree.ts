// -*- coding: utf-8 -*-
/**
 * 组成区纯逻辑（INT-1833 · 规范 18 §4，与 React `domain/lib/container-composition.ts` 同口径）。
 *
 * source 端点只到 id 级（§11-8 的 result_type / execution_status / evaluated /
 * result_created_at 未落地），用例名 / 设备名 / API 名 / 分组 / 标签由容器详情
 * `cases[] / devices[] / apis[]` 按 `source_case_id / source_device_id / source_api_id` join。
 *
 * 同源不变量（§0.3 / §4.2）：四视图**直接复用** P0 的 `cartTree.buildCartView` 四视图层级函数
 * （条目映射成购物车同构分组后传入），组成区不另造一套树；用例层组织（分组 / 标签 × 平铺 / 交叉）
 * 同样由该函数产出，`organizeCompositionCases` 只是把同一棵树投影成组织分组（不重复聚合口径）。
 *
 * 只读语义：容器是既成事实，组成区不渲染复选框、无「移除该组」。
 */
import type {
  PickCartGroup,
  PickCartItem,
  PickSource,
  PickSourceGroup,
} from '../../../infrastructure/api/cherryPickApi';
import type {
  CompositionEntry,
  CompositionEvaluationFilter,
  CompositionExecutionFilter,
  CompositionMissingFilter,
  CompositionSummary,
} from '../../../domain/model/containerComposition';
import type { PickCaseOrgInfo } from './pickTree';
import {
  buildCartCaseView,
  buildCartDeviceView,
  buildCartResultTypeView,
  buildCartTaskView,
  buildCartView,
  type CartOrgDim,
  type CartOrgSubView,
  type CartTreeNode,
  type CartViewMode,
} from './cartTree';
import { UNGROUPED_BUCKET_KEY, UNTAGGED_BUCKET_KEY } from '../../../domain/lib/subViewAggregation';

// ===== 详情侧 join 入参（容器详情 GET /tasks/{id} 的 cases[] / devices[] / apis[]） =====

/** 详情用例行（容器用例行；状态降级数据源 + 用例名 / 分组 / 标签 join 源） */
export interface CompositionCaseRow {
  caseId?: string | number | null
  name?: string | null
  groupName?: string | null
  tags?: string[] | null
  executionStatus?: string | null
  evaluationStatus?: string | null
}

/** 详情设备 / API 行（名称 join 源） */
export interface CompositionResourceRow {
  id: number | string
  name?: string | null
}

/** 缺名用例的展示降级文案（§4.5：不裸显 UUID） */
export const UNKNOWN_CASE_LABEL = '未知用例';

/** 结果类型缺省文案（§4.6：结果级字段未落地 → 全部折叠） */
export const UNKNOWN_RESULT_TYPE_LABEL = '结果类型待补充';

// ===== 数据装配 =====

/**
 * 容器溯源 + 容器详情 → 组成条目（§4.1/§4.6）。
 *
 * - 名 / 分组 / 标签：详情 join（不受 §11-8 契约阻塞；实测容器用例行已带 group_name / tags）；
 * - executionStatus / evaluated：优先取 source 结果级字段（§11-8 落地后自动生效），
 *   未返时降级取同 source_case_id 的容器用例行；
 * - resultType：只取结果级 `result_type`（未落地 → null，展示「结果类型待补充」）；
 * - resultCreatedAt：只取 §11-8 的 `result_created_at`，**绝不**取 `results[].created_at`。
 */
export function toCompositionEntries(
  source: PickSource | null,
  cases: CompositionCaseRow[] = [],
  devices: CompositionResourceRow[] = [],
  apis: CompositionResourceRow[] = [],
): CompositionEntry[] {
  if (!source || !Array.isArray(source.groups)) return [];

  const caseMap = new Map<string, CompositionCaseRow>();
  for (const c of cases) {
    if (c?.caseId !== null && c?.caseId !== undefined) caseMap.set(String(c.caseId), c);
  }
  const deviceMap = new Map<number, CompositionResourceRow>();
  for (const d of devices) {
    if (d?.id !== null && d?.id !== undefined) deviceMap.set(Number(d.id), d);
  }
  const apiMap = new Map<number, CompositionResourceRow>();
  for (const a of apis) {
    if (a?.id !== null && a?.id !== undefined) apiMap.set(Number(a.id), a);
  }

  const entries: CompositionEntry[] = [];
  for (const group of source.groups) {
    const taskId = Number(group.sourceTaskId);
    const taskName = group.sourceTaskName || `任务 ${taskId}`;
    for (const result of group.results ?? []) {
      entries.push(toEntry(result, taskId, taskName, caseMap, deviceMap, apiMap));
    }
  }
  return entries;
}

function toEntry(
  result: PickSourceGroup['results'][number],
  sourceTaskId: number,
  sourceTaskName: string,
  cases: Map<string, CompositionCaseRow>,
  devices: Map<number, CompositionResourceRow>,
  apis: Map<number, CompositionResourceRow>,
): CompositionEntry {
  const sourceCaseId = result?.sourceCaseId ?? null;
  const caseRow = sourceCaseId ? cases.get(String(sourceCaseId)) ?? null : null;
  const deviceRow =
    result?.sourceDeviceId !== null && result?.sourceDeviceId !== undefined
      ? devices.get(Number(result.sourceDeviceId)) ?? null
      : null;
  const apiRow =
    result?.sourceApiId !== null && result?.sourceApiId !== undefined
      ? apis.get(Number(result.sourceApiId)) ?? null
      : null;

  // §4.6 降级口径：结果级字段未返 → 取同 source_case_id 的容器用例行
  const statusFromCase = result?.executionStatus === null || result?.executionStatus === undefined;
  const evaluationFromCase = result?.evaluated === null || result?.evaluated === undefined;

  return {
    resultId: Number(result?.resultId ?? result?.id ?? 0),
    sourceTaskId,
    sourceTaskName,
    sourceCaseId,
    sourceCaseName: result?.caseName ?? caseRow?.name ?? null,
    sourceDeviceId: result?.sourceDeviceId ?? null,
    sourceDeviceName: result?.deviceName ?? deviceRow?.name ?? null,
    sourceApiId: result?.sourceApiId ?? null,
    sourceApiName: result?.apiName ?? apiRow?.name ?? null,
    resultType: result?.resultType ?? null,
    executionStatus: result?.executionStatus ?? caseRow?.executionStatus ?? null,
    // 未知（无容器用例行）→ null，叶行不显示评估徽章
    evaluated: result?.evaluated ?? (caseRow ? caseRow.evaluationStatus === 'completed' : null),
    missing: result?.missing === true,
    // §4.6：只认 §11-8 的 result_created_at（关系行 created_at 不是源结果时间）
    resultCreatedAt: result?.resultCreatedAt ?? null,
    groupName: caseRow?.groupName ?? null,
    tags: Array.isArray(caseRow?.tags) ? [...(caseRow?.tags as string[])] : [],
    statusFromCase,
    evaluationFromCase,
    // §5 用例卡一致性判定用：容器用例行自身继承的执行状态（与叶状态可能不一致）
    caseExecutionStatus: caseRow?.executionStatus ?? null,
    caseEvaluationStatus: caseRow?.evaluationStatus ?? null,
  };
}

// ===== 购物车同构映射（复用 P0 四视图的桥梁） =====

/** 组成条目 → 购物车条目（叶 id 取 resultId；组织分组键 = 用例分组名，容器详情无 group_id） */
function toCartItem(entry: CompositionEntry): PickCartItem {
  return {
    itemId: entry.resultId,
    resultId: entry.resultId,
    sourceTaskId: entry.sourceTaskId,
    sourceTaskName: entry.sourceTaskName,
    sourceCaseId: entry.sourceCaseId,
    // 缺名降级「未知用例」（不裸显 UUID；用例卡与叶行同一文案）
    sourceCaseName: entry.sourceCaseName ?? UNKNOWN_CASE_LABEL,
    sourceDeviceId: entry.sourceDeviceId,
    sourceDeviceName: entry.sourceDeviceName,
    sourceApiId: entry.sourceApiId,
    sourceResultType: entry.resultType,
    executionStatus: entry.executionStatus,
    tags: entry.tags,
    groupName: entry.groupName,
    groupId: entry.groupName,
    invalid: entry.missing,
  };
}

/** 组成条目 → 按来源任务分组（购物车同构，喂给 P0 四视图 builder） */
export function compositionCartGroups(entries: CompositionEntry[]): PickCartGroup[] {
  const groups = new Map<number, PickCartGroup>();
  for (const entry of entries) {
    const item = toCartItem(entry);
    const existing = groups.get(entry.sourceTaskId);
    if (existing) existing.items.push(item);
    else groups.set(entry.sourceTaskId, {
      sourceTaskId: entry.sourceTaskId,
      sourceTaskName: entry.sourceTaskName,
      items: [item],
    });
  }
  return [...groups.values()];
}

/** 组成条目 → 用例组织字段映射（同一用例跨条目取标签并集、分组取首个非空值） */
export function compositionCaseOrgMap(
  entries: CompositionEntry[],
): Map<string | number, PickCaseOrgInfo> {
  const map = new Map<string | number, PickCaseOrgInfo>();
  for (const entry of entries) {
    if (entry.sourceCaseId === null) continue;
    const prev = map.get(entry.sourceCaseId);
    if (!prev) {
      map.set(entry.sourceCaseId, {
        tags: [...entry.tags],
        // 容器详情只有 group_name → 以组名作稳定分组键（与 organizeCompositionCases 同口径）
        groupId: entry.groupName,
        groupName: entry.groupName,
      });
      continue;
    }
    map.set(entry.sourceCaseId, {
      tags: [...new Set([...(prev.tags ?? []), ...entry.tags])],
      groupId: prev.groupId ?? entry.groupName,
      groupName: prev.groupName ?? entry.groupName,
    });
  }
  return map;
}

// ===== 四视图（复用 P0 同一套层级函数，禁止复制第二份） =====

export interface CompositionViewOptions {
  /** 用例层组织维度（分组视图 / 标签视图，缺省分组视图） */
  org?: CartOrgDim
  /** 用例层子视图（平铺 / 交叉） */
  subView?: CartOrgSubView
}

function buildView(
  view: CartViewMode,
  entries: CompositionEntry[],
  opts: CompositionViewOptions = {},
): CartTreeNode[] {
  return buildCartView(view, compositionCartGroups(entries), {
    org: opts.org,
    subView: opts.subView,
    caseOrgMap: compositionCaseOrgMap(entries),
  });
}

/** 任务视图（默认）：任务 → 用例层组织 → 用例卡 → 设备/API → result_type → 叶 */
export function buildCompositionTaskView(
  entries: CompositionEntry[],
  opts: CompositionViewOptions = {},
): CartTreeNode[] {
  return buildCartTaskView(compositionCartGroups(entries), {
    org: opts.org,
    subView: opts.subView,
    caseOrgMap: compositionCaseOrgMap(entries),
  });
}

/** 用例视图：用例层组织 → 用例卡 → 设备/API → result_type → 任务 → 叶 */
export function buildCompositionCaseView(
  entries: CompositionEntry[],
  opts: CompositionViewOptions = {},
): CartTreeNode[] {
  return buildCartCaseView(compositionCartGroups(entries), {
    org: opts.org,
    subView: opts.subView,
    caseOrgMap: compositionCaseOrgMap(entries),
  });
}

/** 设备视图：设备/API → result_type → 用例层组织 → 用例卡 → 任务 → 叶 */
export function buildCompositionDeviceView(
  entries: CompositionEntry[],
  opts: CompositionViewOptions = {},
): CartTreeNode[] {
  return buildCartDeviceView(compositionCartGroups(entries), {
    org: opts.org,
    subView: opts.subView,
    caseOrgMap: compositionCaseOrgMap(entries),
  });
}

/** 结果类型视图：result_type → 设备/API → 用例层组织 → 用例卡 → 任务 → 叶 */
export function buildCompositionResultTypeView(
  entries: CompositionEntry[],
  opts: CompositionViewOptions = {},
): CartTreeNode[] {
  return buildCartResultTypeView(compositionCartGroups(entries), {
    org: opts.org,
    subView: opts.subView,
    caseOrgMap: compositionCaseOrgMap(entries),
  });
}

/** 视图分发（与 cartTree.buildCartView 同一入口语义） */
export function buildCompositionView(
  view: CartViewMode,
  entries: CompositionEntry[],
  opts: CompositionViewOptions = {},
): CartTreeNode[] {
  return buildView(view, entries, opts);
}

// ===== 用例层组织（四组合，与 React organizeCompositionCases 同口径） =====

/** 组织分组（平铺 = 一层；交叉时 subGroups 为另一维度的子分组，空组不下发） */
export interface CompositionCaseOrgGroup {
  key: string
  label: string
  /** 兜底桶弱化（未分组 / 未设置标签） */
  muted: boolean
  /** 组内命中条目（供调用方计数 / 提示判定） */
  entries: CompositionEntry[]
  subGroups: CompositionCaseOrgGroup[]
}

/**
 * 用例层组织（分组视图 / 标签视图 × 平铺 / 交叉）。
 *
 * 与 React `domain/lib/container-composition.ts` `organizeCompositionCases` 同口径：
 * 先按 groupName / tags 聚合用例单元，交叉子视图改按另一维度再分子组，空组不下发。
 * 实现上直接投影 P0 `buildCartCaseView` 的组织层节点——组织聚合只有一份口径
 * （subViewAggregation 同款纯函数），不复制第二套。
 */
export function organizeCompositionCases(
  entries: CompositionEntry[],
  org: CartOrgDim = 'group',
  subView: CartOrgSubView = 'flat',
): CompositionCaseOrgGroup[] {
  const entryMap = new Map<number, CompositionEntry>(entries.map((e) => [e.resultId, e]));
  const roots = buildCartCaseView(compositionCartGroups(entries), {
    org,
    subView,
    caseOrgMap: compositionCaseOrgMap(entries),
  });

  const toGroup = (node: CartTreeNode): CompositionCaseOrgGroup => ({
    key: String(node.id),
    label: node.name,
    muted: node.muted === true ||
      node.id === UNGROUPED_BUCKET_KEY ||
      node.id === UNTAGGED_BUCKET_KEY,
    entries: node.itemIds
      .map((id) => entryMap.get(id))
      .filter((e): e is CompositionEntry => e !== undefined),
    subGroups: node.level === 'org'
      ? node.children.filter((c) => c.level === 'orgSub').map(toGroup)
      : [],
  });

  return roots.map(toGroup);
}

// ===== 筛选（纯客户端；命中叶保留 + 祖先保留 + 分支计数按命中集重算） =====

/** 单条条目筛选命中（执行状态 / 评估状态 / 失效 facet） */
export function matchesCompositionFilter(
  entry: CompositionEntry,
  execution: CompositionExecutionFilter = 'all',
  evaluation: CompositionEvaluationFilter = 'all',
  missing: CompositionMissingFilter = 'all',
): boolean {
  if (execution !== 'all' && entry.executionStatus !== execution) return false;
  if (evaluation === 'evaluated' && entry.evaluated !== true) return false;
  if (evaluation === 'unevaluated' && entry.evaluated === true) return false;
  if (missing === 'missing' && !entry.missing) return false;
  return true;
}

/** 条目级筛选（摘要 / 计数口径） */
export function filterCompositionEntries(
  entries: CompositionEntry[],
  execution: CompositionExecutionFilter = 'all',
  evaluation: CompositionEvaluationFilter = 'all',
  missing: CompositionMissingFilter = 'all',
): CompositionEntry[] {
  return entries.filter((e) => matchesCompositionFilter(e, execution, evaluation, missing));
}

/**
 * 组成树筛选（§4.2/§5/§7）：命中叶保留 + 保留全部祖先 + 分支计数按命中集重算；
 * 不改变层级结构（节点 key 不变 → 展开态由调用方按 key 保持）。
 * `missing` 维度即顶部 Alert 的「只看失效」——与执行 / 评估同一套语义，不另造筛选。
 */
export function filterCompositionTree(
  roots: CartTreeNode[],
  execution: CompositionExecutionFilter,
  evaluation: CompositionEvaluationFilter,
  entryByResultId: ReadonlyMap<number, CompositionEntry>,
  missing: CompositionMissingFilter = 'all',
): CartTreeNode[] {
  const prune = (node: CartTreeNode): CartTreeNode | null => {
    if (node.children.length === 0) {
      const ids = [
        ...new Set(
          node.itemIds.filter((id) => {
            const entry = entryByResultId.get(id);
            return entry !== undefined
              && matchesCompositionFilter(entry, execution, evaluation, missing);
          }),
        ),
      ];
      if (ids.length === 0) return null;
      return { ...node, itemIds: ids, count: ids.length };
    }
    const children = node.children
      .map(prune)
      .filter((n): n is CartTreeNode => n !== null);
    if (children.length === 0) return null;
    const ids = [...new Set(children.flatMap((c) => c.itemIds))];
    return { ...node, children, itemIds: ids, count: ids.length };
  };

  return roots
    .map(prune)
    .filter((n): n is CartTreeNode => n !== null);
}

// ===== 摘要 / 展示辅助 =====

/** 组成摘要：条数 / 失败 / 未评估 / 失效 / 任务数 / 用例数 / 设备数（按过滤后条目统计） */
export function summarizeComposition(
  entries: CompositionEntry[],
  execution: CompositionExecutionFilter = 'all',
  evaluation: CompositionEvaluationFilter = 'all',
  missing: CompositionMissingFilter = 'all',
): CompositionSummary {
  return summarizeEntries(filterCompositionEntries(entries, execution, evaluation, missing));
}

function summarizeEntries(entries: CompositionEntry[]): CompositionSummary {
  const taskIds = new Set<number>();
  const caseIds = new Set<string>();
  const deviceKeys = new Set<string>();
  let failed = 0;
  let unevaluated = 0;
  let missing = 0;

  for (const e of entries) {
    taskIds.add(e.sourceTaskId);
    if (e.sourceCaseId !== null) caseIds.add(e.sourceCaseId);
    if (e.sourceDeviceId !== null) deviceKeys.add(`device:${e.sourceDeviceId}`);
    else if (e.sourceApiId !== null) deviceKeys.add(`api:${e.sourceApiId}`);
    if (e.executionStatus === 'failed') failed += 1;
    if (e.evaluated !== true) unevaluated += 1;
    if (e.missing) missing += 1;
  }

  return {
    total: entries.length,
    failed,
    unevaluated,
    missing,
    taskCount: taskIds.size,
    caseCount: caseIds.size,
    deviceCount: deviceKeys.size,
  };
}

/** 叶行源结果时间（§4.5，mono `YYYY-MM-DD HH:mm`）；无法解析返回空串（调用方不渲染） */
export function formatCompositionTime(value: string | null | undefined): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** 叶行执行状态文案（§5：已完成 / 已失败 / 已停止） */
export function compositionStatusText(status: string | null | undefined): string {
  switch (status) {
    case 'completed': return '已完成';
    case 'failed': return '已失败';
    case 'stopped': return '已停止';
    case 'running': return '执行中';
    case 'pending': return '待执行';
    default: return status || '未知状态';
  }
}

/** 降级期工具行提示（§4.6：执行 / 评估任一降级即显示） */
export function isCompositionDegraded(entries: CompositionEntry[]): boolean {
  return entries.some((e) => e.statusFromCase || e.evaluationFromCase);
}

// ===== 部分失败 / 未评估呈现（§5、INT-1836） =====

/** 用例卡一致性提示文案（§5 / §11） */
export const CASE_STATUS_INHERIT_TIP = '用例状态继承自来源任务；结果状态以叶行为准';

/**
 * 容器执行状态混态判定（§2.1 列表行 / §5）：**纯前端展示映射**，后端字符串仍是 `failed`。
 *
 * - `partial`：0 < failedCases < caseCount → 「部分失败」（warning + 小圆点）
 * - `all`：failedCases = caseCount（且 > 0）→ 「已失败」
 * - `none`：failedCases = 0 或计数缺失 → 不映射，沿用原执行状态徽章
 */
export type ContainerMixState = 'none' | 'partial' | 'all';

export function containerMixState(
  failedCases: number | null | undefined,
  caseCount: number | null | undefined,
): ContainerMixState {
  if (typeof failedCases !== 'number' || typeof caseCount !== 'number') return 'none';
  if (!Number.isFinite(failedCases) || !Number.isFinite(caseCount)) return 'none';
  if (caseCount <= 0 || failedCases <= 0) return 'none';
  return failedCases >= caseCount ? 'all' : 'partial';
}

/** 分支节点计数后缀（§5：失败 f / 失效 k，按该节点下**过滤后**叶统计） */
export interface CompositionBranchCounts {
  /** 失叶片数（执行状态 failed） */
  failed: number
  /** 失效叶片数（源结果 missing） */
  missing: number
}

export function compositionBranchCounts(
  itemIds: readonly number[],
  entryByResultId: ReadonlyMap<number, CompositionEntry>,
): CompositionBranchCounts {
  let failed = 0;
  let missing = 0;
  const seen = new Set<number>();
  for (const id of itemIds) {
    if (seen.has(id)) continue;
    seen.add(id);
    const entry = entryByResultId.get(id);
    if (!entry) continue;
    if (entry.executionStatus === 'failed') failed += 1;
    if (entry.missing) missing += 1;
  }
  return { failed, missing };
}

/**
 * 用例卡一致性（§5）：容器用例行继承的状态与叶状态不一致 → 卡右上 info 图标。
 *
 * §5 节覆盖「部分失败 / **未评估**」两个维度，故执行与评估两处都判定：
 * - 执行：叶 executionStatus ≠ 用例行继承 executionStatus；
 * - 评估：叶 evaluated ≠（用例行 evaluationStatus === 'completed'）。
 * 叶状态未知（null）不计冲突；降级期叶状态取自用例行时两者恒等（不误报），
 * §11-8 结果级字段落地后按真实源结果状态判定（实测 657：用例行评估已完成后，
 * 所选结果 evaluated=false，即典型一致性冲突）。
 */
export function hasCaseStatusConflict(
  itemIds: readonly number[],
  entryByResultId: ReadonlyMap<number, CompositionEntry>,
): boolean {
  let inheritedExec: string | null = null;
  let inheritedEval: string | null = null;
  const leaves: CompositionEntry[] = [];
  for (const id of itemIds) {
    const entry = entryByResultId.get(id);
    if (!entry) continue;
    leaves.push(entry);
    if (inheritedExec === null && entry.caseExecutionStatus) {
      inheritedExec = entry.caseExecutionStatus;
    }
    if (inheritedEval === null && entry.caseEvaluationStatus) {
      inheritedEval = entry.caseEvaluationStatus;
    }
  }
  const executionConflict = inheritedExec !== null && leaves.some(
    (e) => e.executionStatus !== null && e.executionStatus !== inheritedExec,
  );
  if (executionConflict) return true;
  if (inheritedEval === null) return false;
  const inheritedEvaluated = inheritedEval === 'completed';
  return leaves.some((e) => e.evaluated !== null && e.evaluated !== inheritedEvaluated);
}

// ===== §4.6 降级期提示：会话内一次性关闭（模块级，组件卸载 / 重挂保持） =====

let degradedHintDismissed = false;

/** 降级期提示是否已在**本次会话**内关闭 */
export function isDegradedHintDismissed(): boolean {
  return degradedHintDismissed;
}

/** 关闭降级期提示（会话内不再出现） */
export function dismissDegradedHint(): void {
  degradedHintDismissed = true;
}

/** 重置关闭态（测试隔离用；正常交互不调用） */
export function resetDegradedHintDismissed(): void {
  degradedHintDismissed = false;
}

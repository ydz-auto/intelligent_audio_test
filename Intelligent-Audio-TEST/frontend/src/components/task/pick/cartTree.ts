// -*- coding: utf-8 -*-
/**
 * 购物车树纯逻辑（INT-577 §4.2，INT-1831 四视图基座）。
 *
 * 四视图层级照《UX设计规范-VUE 18_挑选合并_合并后任务呈现》§3.2（与 React §3.8.3 A/B 逐字一致）：
 *   任务视图（默认）  任务 → 用例层组织 → 用例卡 → 设备/API → result_type → 叶
 *   用例视图          用例层组织 → 用例卡 → 设备/API → result_type → 任务 → 叶
 *   设备视图          设备/API → result_type → 用例层组织 → 用例卡 → 任务 → 叶
 *   结果类型视图      result_type → 设备/API → 用例层组织 → 用例卡 → 任务 → 叶
 *
 * 叶 = 购物车条目（item_id），节点选中态以叶 item_id 集派生；四视图共用同一份 item_id 集，
 * 切换视图不丢勾选、不改提交载荷。
 * 用例层组织（分组视图 / 标签视图 × 平铺 / 交叉）与挑选侧同口径（INT-1110 §3.8.3）：
 * 组织字段优先取购物车条目自身（items[] 随条目返回 tags / group_id / group_name），
 * 会话缓存仅作补充（resolveCartCaseOrgMap）；缺字段落「未分组」/「未设置标签」兜底桶；空组不下发。
 * 任务层恒渲染（含单来源任务）；组织层在四视图内都存在（INT-1725 口径）。
 */
import type { PickCartGroup, PickCartItem } from '../../../infrastructure/api/cherryPickApi';
import type { PickCaseOrgInfo } from './pickTree';
import {
  groupCasesByCaseGroup,
  groupCasesByTag,
  UNGROUPED_BUCKET_KEY,
  UNTAGGED_BUCKET_KEY,
  type CaseSubGroup,
  type SubViewCaseItem,
} from '../../../domain/lib/subViewAggregation';

export type CartLevel = 'task' | 'org' | 'orgSub' | 'case' | 'device' | 'resultType' | 'leaf';

/** 购物车视图（§3.2 四视图；任务视图为默认） */
export type CartViewMode = 'task' | 'case' | 'device' | 'resultType';

/** 用例层组织维度（分组视图 / 标签视图） */
export type CartOrgDim = 'group' | 'tag';

/** 用例层子视图（平铺 / 交叉：分组视图内按标签、标签视图内按用例分组） */
export type CartOrgSubView = 'flat' | 'byTag' | 'byGroup';

export interface CartTreeNode {
  key: string
  level: CartLevel
  id: string | number
  name: string
  kind?: 'device' | 'api'
  /** INT-1110：用例节点 CaseIdBadge（统一用例卡 compact 复用） */
  caseId?: string | null
  /** INT-1110：用例节点算法徽章（快照无字段时缺省 null） */
  algorithmType?: string | null
  /** 用例层组织节点（org = 组织维度桶；orgSub = 交叉子组维度） */
  org?: CartOrgDim
  /** 兜底桶弱化（未分组 / 未设置标签） */
  muted?: boolean
  count: number
  itemIds: number[]
  children: CartTreeNode[]
}

export interface CartViewOptions {
  /** 组织维度（缺省 group） */
  org?: CartOrgDim
  /** 子视图（缺省 flat） */
  subView?: CartOrgSubView
  /** 用例组织字段（case_id → tags/groupId/groupName；缺省全落兜底桶）。
   *  调用方通常用 resolveCartCaseOrgMap 由条目字段派生，会话缓存仅作补充。 */
  caseOrgMap?: ReadonlyMap<string | number, PickCaseOrgInfo>
}

/** result_type 展示文案：缺值/未解析 → 「结果类型待补充」（§3.7.2 快照缺 source_result_type 折叠口径） */
export function cartResultTypeLabel(resultType?: string | null): string {
  if (!resultType) return '结果类型待补充';
  return resultType;
}

// ===== 内部工具 =====

/** 去重叶 item_id（多标签用例会在多个组织桶各呈现一次，节点内仍不重复计数） */
function uniqItemIds(entries: PickCartItem[]): number[] {
  return [...new Set(entries.map((e) => e.itemId))];
}

function caseNameOf(entry?: PickCartItem): string {
  return entry?.sourceCaseName || entry?.sourceCaseId || '未命名用例';
}

function deviceKindOf(entry: PickCartItem): 'device' | 'api' {
  return entry.sourceDeviceId != null ? 'device' : 'api';
}

function deviceIdOf(entry: PickCartItem): number | null {
  return entry.sourceDeviceId ?? entry.sourceApiId ?? null;
}

function deviceNameOf(entry: PickCartItem): string {
  if (entry.sourceDeviceId != null) {
    return entry.sourceDeviceName || `设备 ${entry.sourceDeviceId}`;
  }
  return entry.sourceApiId != null ? `API ${entry.sourceApiId}` : 'API';
}

function groupBy<T, K extends string | number | null>(rows: T[], keyOf: (row: T) => K): Map<K, T[]> {
  const map = new Map<K, T[]>();
  for (const row of rows) {
    const k = keyOf(row);
    const list = map.get(k);
    if (list) list.push(row); else map.set(k, [row]);
  }
  return map;
}

/** 用例单元（一个用例卡片 = 同一源用例在某个容器下的全部条目） */
interface CartCaseUnit {
  caseId: string | null
  units: PickCartItem[]
}

function groupCaseUnits(entries: PickCartItem[]): CartCaseUnit[] {
  return [...groupBy(entries, (e) => e.sourceCaseId ?? null)].map(([caseId, rows]) => ({
    caseId: caseId == null ? null : String(caseId),
    units: rows,
  }));
}

function caseNode(unit: CartCaseUnit, keyPrefix: string, children: CartTreeNode[]): CartTreeNode {
  const ids = uniqItemIds(unit.units);
  return {
    key: `${keyPrefix}|c:${unit.caseId ?? ''}`,
    level: 'case',
    id: unit.caseId ?? '',
    name: caseNameOf(unit.units[0]),
    caseId: unit.caseId,
    count: ids.length,
    itemIds: ids,
    children,
  };
}

// ===== 叶前任务层（用例 / 设备 / 结果类型视图的末级任务层） =====

/** 任务层节点（叶直挂；任务层恒渲染，含单来源任务——§1.3） */
function buildTaskLeafLayer(entries: PickCartItem[], keyPrefix: string): CartTreeNode[] {
  return [...groupBy(entries, (e) => e.sourceTaskId)].map(([taskId, rows]) => {
    const ids = uniqItemIds(rows);
    return {
      key: `${keyPrefix}|t:${taskId}`,
      level: 'task',
      id: taskId as number,
      name: rows[0]?.sourceTaskName || `任务 ${taskId}`,
      count: ids.length,
      itemIds: ids,
      children: [],
    };
  });
}

// ===== 设备/API → result_type 层（任务 / 用例视图共用） =====

/**
 * 设备/API → result_type → 叶（withTask=true 时 result_type 下再挂任务层 → 叶，用例视图口径）。
 */
function buildDeviceResultTypeLayer(
  entries: PickCartItem[],
  keyPrefix: string,
  withTask: boolean,
): CartTreeNode[] {
  return [...groupBy(entries, (e) => `${deviceKindOf(e)}:${deviceIdOf(e) ?? ''}`)].map(([, deviceRows]) => {
    const first = deviceRows[0];
    const kind = deviceKindOf(first);
    const dimId = deviceIdOf(first);
    const deviceKey = `${keyPrefix}|d:${dimId ?? ''}:${kind}`;
    const deviceIds = uniqItemIds(deviceRows);
    const resultTypes: CartTreeNode[] = [...groupBy(deviceRows, (e) => e.sourceResultType ?? '')]
      .map(([rt, rtRows]) => {
        const rtKey = `${deviceKey}|rt:${rt || 'default'}`;
        const rtIds = uniqItemIds(rtRows);
        return {
          key: rtKey,
          level: 'resultType' as CartLevel,
          id: rt || 'default',
          name: cartResultTypeLabel(rt || null),
          count: rtIds.length,
          itemIds: rtIds,
          children: withTask ? buildTaskLeafLayer(rtRows, rtKey) : [],
        };
      });
    return {
      key: deviceKey,
      level: 'device' as CartLevel,
      id: dimId ?? '',
      name: deviceNameOf(first),
      kind,
      count: deviceIds.length,
      itemIds: deviceIds,
      children: resultTypes,
    };
  });
}

/** 用例卡下的设备/result_type 子层（任务 / 用例视图共用） */
function buildCaseChildren(
  unit: CartCaseUnit,
  keyPrefix: string,
  withTask: boolean,
): CartTreeNode[] {
  return buildDeviceResultTypeLayer(unit.units, `${keyPrefix}|c:${unit.caseId ?? ''}`, withTask);
}

// ===== 用例层组织（分组 / 标签 × 平铺 / 交叉，四视图共享） =====

interface OrgCaseItem extends SubViewCaseItem {
  unit: CartCaseUnit
}

function toOrgItems(units: CartCaseUnit[], caseOrgMap?: CartViewOptions['caseOrgMap']): OrgCaseItem[] {
  return units.map((unit) => {
    const info = unit.caseId != null ? caseOrgMap?.get(unit.caseId) : undefined;
    return {
      unit,
      tags: info?.tags ?? [],
      groupId: info?.groupId != null ? String(info.groupId) : null,
      groupName: info?.groupName ?? null,
      totalDuration: null,
    };
  });
}

function isFallbackBucket(key: string): boolean {
  return key === UNGROUPED_BUCKET_KEY || key === UNTAGGED_BUCKET_KEY;
}

function orgBuckets(items: OrgCaseItem[], org: CartOrgDim): CaseSubGroup<OrgCaseItem>[] {
  return org === 'tag' ? groupCasesByTag(items, []) : groupCasesByCaseGroup(items);
}

/**
 * 用例层组织节点（org 桶 → 平铺直挂用例卡 / 交叉再挂 orgSub 子组 → 用例卡）。
 * 空组不下发（桶/子组只由实际命中的用例生成，防御性跳过空桶）。
 */
function buildOrgLayer(
  units: CartCaseUnit[],
  keyPrefix: string,
  opts: CartViewOptions,
  buildCaseNode: (unit: CartCaseUnit, prefix: string) => CartTreeNode,
): CartTreeNode[] {
  const org: CartOrgDim = opts.org ?? 'group';
  const subView: CartOrgSubView = opts.subView ?? 'flat';
  const nodes: CartTreeNode[] = [];
  for (const bucket of orgBuckets(toOrgItems(units, opts.caseOrgMap), org)) {
    if (bucket.cases.length === 0) continue;
    const bucketKey = `${keyPrefix}|org:${org}:${bucket.key}`;
    const bucketEntries = bucket.cases.flatMap((c) => c.unit.units);
    let children: CartTreeNode[];
    if (subView === 'flat') {
      children = bucket.cases.map((c) => buildCaseNode(c.unit, bucketKey));
    } else {
      // 交叉：分组视图内按标签、标签视图内按用例分组（与 PickCaseOrgList 同口径）
      const subDim: CartOrgDim = org === 'group' ? 'tag' : 'group';
      const subBuckets = subDim === 'tag'
        ? groupCasesByTag(bucket.cases, [])
        : groupCasesByCaseGroup(bucket.cases);
      children = subBuckets
        .filter((sg) => sg.cases.length > 0)
        .map((sg) => {
          const subKey = `${bucketKey}|sub:${sg.key}`;
          const subIds = uniqItemIds(sg.cases.flatMap((c) => c.unit.units));
          return {
            key: subKey,
            level: 'orgSub' as CartLevel,
            id: sg.key,
            name: sg.label,
            org: subDim,
            muted: isFallbackBucket(sg.key),
            count: subIds.length,
            itemIds: subIds,
            children: sg.cases.map((c) => buildCaseNode(c.unit, subKey)),
          };
        });
    }
    const bucketIds = uniqItemIds(bucketEntries);
    nodes.push({
      key: bucketKey,
      level: 'org',
      id: bucket.key,
      name: bucket.label,
      org,
      muted: isFallbackBucket(bucket.key),
      count: bucketIds.length,
      itemIds: bucketIds,
      children,
    });
  }
  return nodes;
}

// ===== 四视图 =====

/** 任务视图（默认）：任务 → 用例层组织 → 用例卡 → 设备/API → result_type → 叶 */
export function buildCartTaskView(groups: PickCartGroup[], opts: CartViewOptions = {}): CartTreeNode[] {
  const roots: CartTreeNode[] = [];
  for (const g of groups) {
    if (g.items.length === 0) continue;
    const taskKey = `t:${g.sourceTaskId}`;
    const ids = uniqItemIds(g.items);
    roots.push({
      key: taskKey,
      level: 'task',
      id: g.sourceTaskId,
      name: g.sourceTaskName || `任务 ${g.sourceTaskId}`,
      count: ids.length,
      itemIds: ids,
      children: buildOrgLayer(groupCaseUnits(g.items), taskKey, opts, (unit, prefix) =>
        caseNode(unit, prefix, buildCaseChildren(unit, prefix, false))),
    });
  }
  return roots;
}

/** 用例视图：用例层组织 → 用例卡 → 设备/API → result_type → 任务 → 叶 */
export function buildCartCaseView(groups: PickCartGroup[], opts: CartViewOptions = {}): CartTreeNode[] {
  const all = groups.flatMap((g) => g.items);
  return buildOrgLayer(groupCaseUnits(all), 'cv', opts, (unit, prefix) =>
    caseNode(unit, prefix, buildCaseChildren(unit, prefix, true)));
}

/** 设备视图：设备/API → result_type → 用例层组织 → 用例卡 → 任务 → 叶 */
export function buildCartDeviceView(groups: PickCartGroup[], opts: CartViewOptions = {}): CartTreeNode[] {
  const all = groups.flatMap((g) => g.items);
  return [...groupBy(all, (e) => `${deviceKindOf(e)}:${deviceIdOf(e) ?? ''}`)].map(([, deviceRows]) => {
    const first = deviceRows[0];
    const kind = deviceKindOf(first);
    const dimId = deviceIdOf(first);
    const deviceKey = `dv|d:${dimId ?? ''}:${kind}`;
    const deviceIds = uniqItemIds(deviceRows);
    const resultTypes: CartTreeNode[] = [...groupBy(deviceRows, (e) => e.sourceResultType ?? '')]
      .map(([rt, rtRows]) => {
        const rtKey = `${deviceKey}|rt:${rt || 'default'}`;
        const rtIds = uniqItemIds(rtRows);
        return {
          key: rtKey,
          level: 'resultType' as CartLevel,
          id: rt || 'default',
          name: cartResultTypeLabel(rt || null),
          count: rtIds.length,
          itemIds: rtIds,
          children: buildOrgLayer(groupCaseUnits(rtRows), rtKey, opts, (unit, prefix) =>
            caseNode(unit, prefix, buildTaskLeafLayer(unit.units, `${prefix}|c:${unit.caseId ?? ''}`))),
        };
      });
    return {
      key: deviceKey,
      level: 'device' as CartLevel,
      id: dimId ?? '',
      name: deviceNameOf(first),
      kind,
      count: deviceIds.length,
      itemIds: deviceIds,
      children: resultTypes,
    };
  });
}

/** 结果类型视图：result_type → 设备/API → 用例层组织 → 用例卡 → 任务 → 叶 */
export function buildCartResultTypeView(groups: PickCartGroup[], opts: CartViewOptions = {}): CartTreeNode[] {
  const all = groups.flatMap((g) => g.items);
  return [...groupBy(all, (e) => e.sourceResultType ?? '')].map(([rt, rtRows]) => {
    const rtKey = `rtv|rt:${rt || 'default'}`;
    const rtIds = uniqItemIds(rtRows);
    const devices: CartTreeNode[] = [...groupBy(rtRows, (e) => `${deviceKindOf(e)}:${deviceIdOf(e) ?? ''}`)]
      .map(([, deviceRows]) => {
        const first = deviceRows[0];
        const kind = deviceKindOf(first);
        const dimId = deviceIdOf(first);
        const deviceKey = `${rtKey}|d:${dimId ?? ''}:${kind}`;
        const deviceIds = uniqItemIds(deviceRows);
        return {
          key: deviceKey,
          level: 'device' as CartLevel,
          id: dimId ?? '',
          name: deviceNameOf(first),
          kind,
          count: deviceIds.length,
          itemIds: deviceIds,
          children: buildOrgLayer(groupCaseUnits(deviceRows), deviceKey, opts, (unit, prefix) =>
            caseNode(unit, prefix, buildTaskLeafLayer(unit.units, `${prefix}|c:${unit.caseId ?? ''}`))),
        };
      });
    return {
      key: rtKey,
      level: 'resultType' as CartLevel,
      id: rt || 'default',
      name: cartResultTypeLabel(rt || null),
      count: rtIds.length,
      itemIds: rtIds,
      children: devices,
    };
  });
}

/** 视图分发（四个 view builder 的单一入口，四视图共享同一条目集） */
export function buildCartView(
  view: CartViewMode,
  groups: PickCartGroup[],
  opts: CartViewOptions = {},
): CartTreeNode[] {
  switch (view) {
    case 'case': return buildCartCaseView(groups, opts);
    case 'device': return buildCartDeviceView(groups, opts);
    case 'resultType': return buildCartResultTypeView(groups, opts);
    default: return buildCartTaskView(groups, opts);
  }
}

/**
 * 用例组织字段解析（四视图组织层数据源）。
 *
 * 购物车条目自身已带用例级组织字段（GET /tasks/cherry-picks/cart 的 items[] 随条目
 * 返回 tags / group_id / group_name，与候选项 §11-7 同源）——刷新页面或直接打开抽屉
 * 也按真实分组 / 标签组织；会话缓存（挑选侧载入候选时记入）仅作补充，供历史条目缺字段时兜底。
 * 同一用例跨条目的字段取并集（标签去重；分组取首个非空值）。
 */
export function resolveCartCaseOrgMap(
  groups: PickCartGroup[],
  supplement?: ReadonlyMap<string | number, PickCaseOrgInfo>,
): Map<string | number, PickCaseOrgInfo> {
  const map = new Map<string | number, PickCaseOrgInfo>();
  const upsert = (caseId: string | number, info: PickCaseOrgInfo) => {
    const prev = map.get(caseId);
    if (!prev) {
      map.set(caseId, {
        tags: [...(info.tags ?? [])],
        groupId: info.groupId ?? null,
        groupName: info.groupName ?? null,
      });
      return;
    }
    map.set(caseId, {
      tags: [...new Set([...(prev.tags ?? []), ...(info.tags ?? [])])],
      groupId: prev.groupId ?? info.groupId ?? null,
      groupName: prev.groupName ?? info.groupName ?? null,
    });
  };
  for (const g of groups) {
    for (const it of g.items) {
      if (!it.sourceCaseId) continue;
      const tags = it.tags ?? [];
      const groupName = it.groupName ?? null;
      const groupId = it.groupId != null ? String(it.groupId) : null;
      if (tags.length === 0 && groupName == null && groupId == null) continue;
      upsert(it.sourceCaseId, { tags, groupId, groupName });
    }
  }
  if (supplement) {
    for (const [caseId, info] of supplement) upsert(caseId, info);
  }
  return map;
}

/**
 * 购物车是否有用例组织字段（四视图组织层兜底提示判定）。
 * 优先看条目自身字段（刷新 / 直接进抽屉），会话缓存补充命中同样算有数据；
 * 全缺时组织层只有单兜底桶，工具行显示兜底提示（与挑选侧 §11-7 同口径）。
 */
export function hasCartCaseOrg(
  groups: PickCartGroup[],
  caseOrgMap?: CartViewOptions['caseOrgMap'],
): boolean {
  const has = (info?: PickCaseOrgInfo | null): boolean =>
    !!info && (!!info.groupName || info.groupId != null || (info.tags?.length ?? 0) > 0);
  for (const g of groups) {
    for (const it of g.items) {
      if (has({ tags: it.tags ?? [], groupId: it.groupId ?? null, groupName: it.groupName ?? null })) return true;
      const info = it.sourceCaseId ? caseOrgMap?.get(it.sourceCaseId) : undefined;
      if (has(info)) return true;
    }
  }
  return false;
}

/** 收集可展开节点 key（全部展开 / 全部收起；叶前一层不参与） */
export function collectCartNodeKeys(roots: CartTreeNode[]): string[] {
  const out: string[] = [];
  const walk = (nodes: CartTreeNode[]) => {
    for (const node of nodes) {
      if (node.children.length === 0) continue;
      out.push(node.key);
      walk(node.children);
    }
  };
  walk(roots);
  return out;
}

export type CartNodeCheckState = 'checked' | 'indeterminate' | 'unchecked';

/** 节点三态派生（selectedItemIds 为唯一真相，四视图共用） */
export function cartNodeState(node: CartTreeNode, selected: ReadonlySet<number>): CartNodeCheckState {
  const ids = [...new Set(node.itemIds)];
  let hit = 0;
  for (const id of ids) {
    if (selected.has(id)) hit += 1;
  }
  if (hit === 0) return 'unchecked';
  if (hit === ids.length) return 'checked';
  return 'indeterminate';
}

/** 勾选/取消节点（批量移除选择 R1-R5 同构；四视图切换不丢勾选） */
export function toggleCartNode(node: CartTreeNode, selected: ReadonlySet<number>): Set<number> {
  const next = new Set(selected);
  const state = cartNodeState(node, selected);
  if (state === 'checked') {
    for (const id of node.itemIds) next.delete(id);
  } else {
    for (const id of node.itemIds) next.add(id);
  }
  return next;
}

/** 节点叶 item_id（节点移除/勾选） */
export function collectCartLeafIds(node: CartTreeNode): number[] {
  return [...new Set(node.itemIds)];
}

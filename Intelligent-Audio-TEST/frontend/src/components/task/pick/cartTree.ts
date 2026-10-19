// -*- coding: utf-8 -*-
/**
 * 购物车树纯逻辑（INT-577 §4.2）——按来源任务→用例→设备/API→result_type 分组，
 * 与挑选页同级口径；叶 = 购物车条目（item_id），节点选中态以叶 item_id 集派生。
 *
 * 分组维度依赖购物车快照字段：source_case_name/source_device_name/source_api_id/
 * source_result_type（§11-5 补齐；缺名容错显示 ID）。
 */
import type { PickCartGroup } from '../../../infrastructure/api/cherryPickApi';

export interface CartTreeNode {
  key: string
  level: 'task' | 'case' | 'device' | 'resultType' | 'leaf'
  id: string | number
  name: string
  kind?: 'device' | 'api'
  count: number
  itemIds: number[]
  children: CartTreeNode[]
}

/** result_type 展示文案：缺值/未解析 → 「结果类型待补充」（§3.7.2 快照缺 source_result_type 折叠口径） */
export function cartResultTypeLabel(resultType?: string | null): string {
  if (!resultType) return '结果类型待补充';
  return resultType;
}

/** 购物车 → 树（任务→用例→设备/API→result_type；叶=条目） */
export function buildCartTree(groups: PickCartGroup[]): CartTreeNode[] {
  const roots: CartTreeNode[] = [];
  const rootByKey = new Map<string, CartTreeNode>();
  for (const g of groups) {
    const tKey = `t:${g.sourceTaskId}`;
    let task = rootByKey.get(tKey);
    if (!task) {
      task = {
        key: tKey, level: 'task', id: g.sourceTaskId,
        name: g.sourceTaskName || `任务 ${g.sourceTaskId}`,
        count: 0, itemIds: [], children: [],
      };
      rootByKey.set(tKey, task);
      roots.push(task);
    }
    for (const it of g.items) {
      const caseKey = `${tKey}|c:${it.sourceCaseId ?? ''}`;
      let caseNode = task.children.find((n) => n.key === caseKey);
      if (!caseNode) {
        caseNode = {
          key: caseKey, level: 'case', id: it.sourceCaseId ?? '',
          name: it.sourceCaseName || it.sourceCaseId || '未命名用例',
          count: 0, itemIds: [], children: [],
        };
        task.children.push(caseNode);
      }
      const deviceId = it.sourceDeviceId ?? null;
      const apiId = it.sourceApiId ?? null;
      const kind: 'device' | 'api' = deviceId != null ? 'device' : 'api';
      const dimId = deviceId ?? apiId;
      const dimKey = `${caseKey}|d:${dimId ?? ''}:${kind}`;
      let dimNode = caseNode.children.find((n) => n.key === dimKey);
      if (!dimNode) {
        dimNode = {
          key: dimKey, level: 'device', id: dimId ?? '',
          name: kind === 'device' ? (it.sourceDeviceName || `设备 ${dimId}`) : (it.sourceApiId != null ? `API ${it.sourceApiId}` : 'API'),
          kind, count: 0, itemIds: [], children: [],
        };
        caseNode.children.push(dimNode);
      }
      const rtKey = `${dimKey}|rt:${it.sourceResultType ?? 'default'}`;
      let rtNode = dimNode.children.find((n) => n.key === rtKey);
      if (!rtNode) {
        rtNode = {
          key: rtKey, level: 'resultType', id: it.sourceResultType ?? 'default',
          name: cartResultTypeLabel(it.sourceResultType), count: 0, itemIds: [], children: [],
        };
        dimNode.children.push(rtNode);
      }
      rtNode.itemIds.push(it.itemId);
      rtNode.count += 1;
      dimNode.itemIds.push(it.itemId);
      dimNode.count += 1;
      caseNode.itemIds.push(it.itemId);
      caseNode.count += 1;
      task.itemIds.push(it.itemId);
      task.count += 1;
    }
  }
  return roots;
}

export type CartNodeCheckState = 'checked' | 'indeterminate' | 'unchecked';

/** 节点三态派生（selectedItemIds 为唯一真相） */
export function cartNodeState(node: CartTreeNode, selected: ReadonlySet<number>): CartNodeCheckState {
  let hit = 0;
  for (const id of node.itemIds) {
    if (selected.has(id)) hit += 1;
  }
  if (hit === 0) return 'unchecked';
  if (hit === node.itemIds.length) return 'checked';
  return 'indeterminate';
}

/** 勾选/取消节点（批量移除选择 R1-R5 同构） */
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

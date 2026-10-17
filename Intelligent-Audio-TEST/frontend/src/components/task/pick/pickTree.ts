// -*- coding: utf-8 -*-
/**
 * 挑选树纯逻辑（INT-577 §3）——四级分组（任务→用例→设备/API→result_type）+ 结果行叶。
 *
 * 树由平铺候选行重建（§11-3 未落地前口径）：候选行已携带 case_name/device_name/
 * api_name/result_type（后端 §11-2 补字段），无缺名时按 ID 容错展示。
 *
 * 选中态以叶 result_id 集为唯一真相（selectedResultIds），节点三态全量派生，
 * 联动规则 R1-R10 由此统一实现：
 *   R1/R6/R7 勾选父级=加入其全部子孙叶；R2 取消父级=移除其全部子孙叶；
 *   R3 子级勾选→父级部分/全选派生；R4 取消 device 清其下 result_type 与叶；
 *   R5 取消 result_type 仅清其下叶（device 保持部分）；R8 跨任务独立；
 *   R9 全选当前筛选/反选；R10 已加购标记由 resultIdSet 派生。
 */
import type { PickCandidate } from '../../../infrastructure/api/cherryPickApi';

export type PickLevel = 'task' | 'case' | 'device' | 'resultType' | 'leaf';

export interface PickTreeNode {
  key: string
  level: PickLevel
  id: string | number
  name: string
  /** 设备节点标识（device|api 二选一，节点区分用） */
  kind?: 'device' | 'api'
  count: number
  resultIds: number[]
  children: PickTreeNode[]
}

/** 由平铺候选行重建四级树（设备/API 同级并列；result_type 缺省 default） */
export function buildPickTree(candidates: PickCandidate[]): PickTreeNode[] {
  const roots: PickTreeNode[] = [];
  const rootByKey = new Map<string, PickTreeNode>();
  for (const c of candidates) {
    const tKey = `t:${c.taskId}`;
    let task = rootByKey.get(tKey);
    if (!task) {
      task = {
        key: tKey, level: 'task', id: c.taskId, name: c.taskName || `任务 ${c.taskId}`,
        count: 0, resultIds: [], children: [],
      };
      rootByKey.set(tKey, task);
      roots.push(task);
    }
    const caseKey = `${tKey}|c:${c.caseId}`;
    let caseNode = task.children.find((n) => n.key === caseKey);
    if (!caseNode) {
      caseNode = {
        key: caseKey, level: 'case', id: c.caseId,
        name: c.caseName || c.caseId, count: 0, resultIds: [], children: [],
      };
      task.children.push(caseNode);
    }
    const deviceId = c.deviceId ?? null;
    const apiId = c.apiId ?? null;
    const kind: 'device' | 'api' = deviceId != null ? 'device' : 'api';
    const dimId = deviceId ?? apiId;
    const dimKey = `${caseKey}|d:${dimId}:${kind}`;
    let dimNode = caseNode.children.find((n) => n.key === dimKey);
    if (!dimNode) {
      dimNode = {
        key: dimKey, level: 'device', id: dimId ?? '',
        name: kind === 'device' ? (c.deviceName || `设备 ${dimId}`) : (c.apiName || `API ${dimId}`),
        kind, count: 0, resultIds: [], children: [],
      };
      caseNode.children.push(dimNode);
    }
    const rtKey = `${dimKey}|rt:${c.resultType ?? 'default'}`;
    let rtNode = dimNode.children.find((n) => n.key === rtKey);
    if (!rtNode) {
      rtNode = {
        key: rtKey, level: 'resultType', id: c.resultType ?? 'default',
        name: c.resultType ?? 'default', count: 0, resultIds: [], children: [],
      };
      dimNode.children.push(rtNode);
    }
    rtNode.resultIds.push(c.resultId);
    rtNode.count += 1;
    dimNode.resultIds.push(c.resultId);
    dimNode.count += 1;
    caseNode.resultIds.push(c.resultId);
    caseNode.count += 1;
    task.resultIds.push(c.resultId);
    task.count += 1;
  }
  return roots;
}

export type NodeCheckState = 'checked' | 'indeterminate' | 'unchecked';

/** 节点三态派生（selectedResultIds 为唯一真相） */
export function nodeState(node: PickTreeNode, selected: ReadonlySet<number>): NodeCheckState {
  let hit = 0;
  for (const rid of node.resultIds) {
    if (selected.has(rid)) hit += 1;
  }
  if (hit === 0) return 'unchecked';
  if (hit === node.resultIds.length) return 'checked';
  return 'indeterminate';
}

/** 勾选/取消节点（R1/R2 及各级；返回新的选中集） */
export function toggleNode(node: PickTreeNode, selected: ReadonlySet<number>): Set<number> {
  const next = new Set(selected);
  const state = nodeState(node, selected);
  if (state === 'checked') {
    for (const rid of node.resultIds) next.delete(rid);
  } else {
    for (const rid of node.resultIds) next.add(rid);
  }
  return next;
}

/** R9 全选当前筛选：加入全部命中叶 */
export function selectAll(leaves: number[], selected: ReadonlySet<number>): Set<number> {
  const next = new Set(selected);
  for (const rid of leaves) next.add(rid);
  return next;
}

/** R9 反选：仅对给定叶取反，保留其余跨页已选 */
export function invertSelection(leaves: number[], selected: ReadonlySet<number>): Set<number> {
  const next = new Set(selected);
  for (const rid of leaves) {
    if (next.has(rid)) next.delete(rid); else next.add(rid);
  }
  return next;
}

/** 展开全部叶 result_id（树重建后全选/反选用） */
export function collectLeafResultIds(roots: PickTreeNode[]): number[] {
  const out: number[] = [];
  const walk = (nodes: PickTreeNode[]) => {
    for (const n of nodes) {
      if (n.level === 'leaf' || n.children.length === 0) {
        out.push(...n.resultIds);
      } else {
        walk(n.children);
      }
    }
  };
  walk(roots);
  return out;
}

/** 展开树节点叶 result_id（节点移除/勾选用） */
export function collectResultIds(node: PickTreeNode): number[] {
  return [...node.resultIds];
}

// -*- coding: utf-8 -*-
/**
 * 购物车树纯逻辑测试（INT-577 §4.2，INT-1831 四视图基座）。
 * 四视图层级照《UX设计规范-VUE 18_挑选合并_合并后任务呈现》§3.2：
 *   任务视图  任务 → 用例层组织 → 用例卡 → 设备/API → result_type → 叶
 *   用例视图  用例层组织 → 用例卡 → 设备/API → result_type → 任务 → 叶
 *   设备视图  设备/API → result_type → 用例层组织 → 用例卡 → 任务 → 叶
 *   结果类型视图 result_type → 设备/API → 用例层组织 → 用例卡 → 任务 → 叶
 */
import { describe, it, expect } from 'vitest';
import {
  buildCartTaskView, buildCartCaseView, buildCartDeviceView, buildCartResultTypeView, buildCartView,
  cartNodeState, toggleCartNode, collectCartNodeKeys, hasCartCaseOrg, resolveCartCaseOrgMap,
  type CartTreeNode,
} from '../cartTree';
import type { PickCartGroup } from '../../../../infrastructure/api/cherryPickApi';
import type { PickCaseOrgInfo } from '../pickTree';

function group(sourceTaskId: number, sourceTaskName: string, items: Array<Record<string, unknown>>): PickCartGroup {
  return { sourceTaskId, sourceTaskName, items: items as any };
}

/** 两个来源任务：任务A 里 C1 两个 result_type + C2；任务B 里 C1 再次出现（跨任务同用例） */
const groups: PickCartGroup[] = [
  group(1, '任务A', [
    { itemId: 1, resultId: 11, sourceTaskId: 1, sourceTaskName: '任务A', sourceCaseId: 'C1', sourceCaseName: '用例1', sourceDeviceId: 7, sourceDeviceName: '设备7', sourceResultType: 'real-time' },
    { itemId: 2, resultId: 12, sourceTaskId: 1, sourceTaskName: '任务A', sourceCaseId: 'C1', sourceCaseName: '用例1', sourceDeviceId: 7, sourceDeviceName: '设备7', sourceResultType: 'final' },
    { itemId: 3, resultId: 13, sourceTaskId: 1, sourceTaskName: '任务A', sourceCaseId: 'C2', sourceCaseName: '用例2', sourceDeviceId: 8, sourceDeviceName: '设备8', sourceResultType: 'final' },
  ]),
  group(2, '任务B', [
    { itemId: 4, resultId: 14, sourceTaskId: 2, sourceTaskName: '任务B', sourceCaseId: 'C1', sourceCaseName: '用例1', sourceDeviceId: 9, sourceDeviceName: '设备9', sourceResultType: 'real-time' },
  ]),
];

const caseOrgMap = new Map<string | number, PickCaseOrgInfo>([
  ['C1', { tags: ['标签A'], groupId: 'g1', groupName: '分组一' }],
  ['C2', { tags: [], groupId: 'g1', groupName: '分组一' }],
]);

const labels = (nodes: CartTreeNode[]) => nodes.map((n) => `${n.level}:${n.name}`);

describe('任务视图（默认）：任务 → 用例层组织 → 用例卡 → 设备/API → result_type → 叶', () => {
  const tree = buildCartTaskView(groups, { caseOrgMap });

  it('任务层在首级，其下是用例层组织桶，桶内是用例卡', () => {
    expect(tree.map((n) => n.level)).toEqual(['task', 'task']);
    expect(tree[0].name).toBe('任务A');
    expect(tree[0].children.map((n) => n.level)).toEqual(['org']);
    const bucket = tree[0].children[0];
    expect(bucket.name).toBe('分组一');
    expect(bucket.children.map((n) => `${n.level}:${n.name}`)).toEqual(['case:用例1', 'case:用例2']);
  });

  it('用例卡下是设备/API → result_type，result_type 为叶前一层（持 item_id）', () => {
    const c1 = tree[0].children[0].children[0];
    expect(c1.level).toBe('case');
    expect(c1.children).toHaveLength(1);
    const device = c1.children[0];
    expect(device.level).toBe('device');
    expect(device.name).toBe('设备7');
    expect(device.children.map((n) => `${n.level}:${n.name}`)).toEqual(['resultType:real-time', 'resultType:final']);
    expect(device.children[0].children).toEqual([]);
    expect(device.children[0].itemIds).toEqual([1]);
  });

  it('各层计数按条目重算（任务层不因多组织桶重复计数）', () => {
    expect(tree[0].count).toBe(3);
    expect(tree[0].children[0].count).toBe(3);
    expect(tree[0].children[0].children[0].count).toBe(2);
    const device = tree[0].children[0].children[0].children[0];
    expect(device.count).toBe(2);
    expect(device.children.map((n) => n.count)).toEqual([1, 1]);
  });
});

describe('用例视图：用例层组织 → 用例卡 → 设备/API → result_type → 任务 → 叶', () => {
  const tree = buildCartCaseView(groups, { caseOrgMap });

  it('组织桶为首级（跨来源任务聚合同一用例）', () => {
    expect(tree.map((n) => n.level)).toEqual(['org']);
    const bucket = tree[0];
    expect(bucket.children.map((n) => n.name)).toEqual(['用例1', '用例2']);
    // 用例1 跨任务A/B 聚合：3 条
    expect(bucket.children[0].count).toBe(3);
  });

  it('每张用例卡都带任务层（任务层恒渲染，含单来源任务）', () => {
    const c1 = tree[0].children[0];
    expect(c1.count).toBe(3); // 任务A 两条 + 任务B 一条
    const device = c1.children[0];
    expect(device.level).toBe('device');
    const rt = device.children[0];
    expect(rt.level).toBe('resultType');
    expect(rt.children.map((n) => `${n.level}:${n.name}`)).toEqual(['task:任务A']);
    // 任务层为叶前一层
    expect(rt.children[0].children).toEqual([]);
    expect(rt.children[0].itemIds).toEqual([1]);
    // 任务B 的同一用例经另一设备进入同一用例卡
    expect(c1.children.map((n) => n.name)).toEqual(['设备7', '设备9']);
    expect(c1.children[1].children[0].children.map((n) => n.name)).toEqual(['任务B']);
  });

  it('单来源任务同样渲染任务层（用例2 只来自任务A）', () => {
    const c2 = tree[0].children[1];
    const tasks = c2.children[0].children[0].children;
    expect(tasks.map((n) => n.level)).toEqual(['task']);
    expect(tasks[0].name).toBe('任务A');
  });
});

describe('设备视图：设备/API → result_type → 用例层组织 → 用例卡 → 任务 → 叶', () => {
  const tree = buildCartDeviceView(groups, { caseOrgMap });

  it('设备为首级，result_type 之下才出现用例层组织与用例卡', () => {
    expect(tree.map((n) => `${n.level}:${n.name}`)).toEqual(['device:设备7', 'device:设备8', 'device:设备9']);
    const rt = tree[0].children[0];
    expect(rt.level).toBe('resultType');
    expect(rt.children.map((n) => `${n.level}:${n.name}`)).toEqual(['org:分组一']);
    const caseNode = rt.children[0].children[0];
    expect(caseNode.level).toBe('case');
    expect(labels(caseNode.children)).toEqual(['task:任务A']);
    expect(caseNode.children[0].children).toEqual([]);
  });
});

describe('结果类型视图：result_type → 设备/API → 用例层组织 → 用例卡 → 任务 → 叶', () => {
  const tree = buildCartResultTypeView(groups, { caseOrgMap });

  it('result_type 为首级，设备之下是用例层组织，末级任务层后是叶', () => {
    expect(tree.map((n) => `${n.level}:${n.name}`)).toEqual(['resultType:real-time', 'resultType:final']);
    const device = tree[0].children[0];
    expect(device.level).toBe('device');
    expect(device.children.map((n) => `${n.level}:${n.name}`)).toEqual(['org:分组一']);
    const caseNode = device.children[0].children[0];
    expect(caseNode.level).toBe('case');
    expect(caseNode.children.map((n) => n.level)).toEqual(['task']);
    expect(caseNode.children[0].itemIds).toEqual([1]);
  });
});

describe('用例层组织：分组 / 标签 × 平铺 / 交叉，空组不下发', () => {
  it('标签视图：多标签用例在各标签桶各呈现一次，无标签落「未设置标签」', () => {
    const map = new Map<string | number, PickCaseOrgInfo>([
      ['C1', { tags: ['标签A', '标签B'], groupId: 'g1', groupName: '分组一' }],
      ['C2', { tags: [], groupId: 'g1', groupName: '分组一' }],
    ]);
    const tree = buildCartCaseView(groups, { org: 'tag', caseOrgMap: map });
    expect(tree.map((n) => n.name)).toEqual(['标签A', '标签B', '未设置标签']);
    // 标签A 只有用例1；未设置标签只有用例2
    expect(tree[0].children.map((n) => n.name)).toEqual(['用例1']);
    expect(tree[2].children.map((n) => n.name)).toEqual(['用例2']);
    expect(tree[2].muted).toBe(true);
  });

  it('交叉（标签视图 → 按用例分组）：桶内再分子组，只出现真实组合', () => {
    const map = new Map<string | number, PickCaseOrgInfo>([
      ['C1', { tags: ['标签A'], groupId: 'g1', groupName: '分组一' }],
      ['C2', { tags: ['标签A'], groupId: 'g2', groupName: '分组二' }],
    ]);
    const tree = buildCartCaseView(groups, { org: 'tag', subView: 'byGroup', caseOrgMap: map });
    expect(tree).toHaveLength(1); // 只有「标签A」一个桶
    const subLabels = tree[0].children.map((n) => `${n.level}:${n.name}`);
    expect([...subLabels].sort()).toEqual(['orgSub:分组一', 'orgSub:分组二']);
    // 只出现真实组合：分组一桶内只有用例1，分组二桶内只有用例2
    const subOf = (name: string) => tree[0].children.find((n) => n.name === name)!;
    expect(subOf('分组一').children.map((n) => n.name)).toEqual(['用例1']);
    expect(subOf('分组二').children.map((n) => n.name)).toEqual(['用例2']);
  });

  it('组织字段全缺省 → 单兜底桶，且不出现空桶', () => {
    const tree = buildCartTaskView(groups, {});
    const bucket = tree[0].children;
    expect(bucket.map((n) => n.name)).toEqual(['未分组']);
    expect(bucket[0].muted).toBe(true);
    expect(bucket[0].children).toHaveLength(2);
    expect(bucket.flatMap((b) => b.children).every((c) => c.children.length > 0)).toBe(true);
  });

  it('空条目分组不下发（空购物车 → 空树）', () => {
    expect(buildCartView('task', [], {})).toEqual([]);
    expect(buildCartView('case', [group(9, '空任务', [])], {})).toEqual([]);
  });
});

describe('用例层组织字段来源：条目自身为主，会话缓存仅补充（审计 P2-1）', () => {
  /** 条目自带组织字段（购物车接口随条目返回 tags / group_id / group_name） */
  const groupsWithOrg: PickCartGroup[] = [
    group(1, '任务A', [
      { itemId: 1, resultId: 11, sourceTaskId: 1, sourceTaskName: '任务A', sourceCaseId: 'C1', sourceCaseName: '用例1', sourceDeviceId: 7, sourceDeviceName: '设备7', sourceResultType: 'default', tags: ['标签A'], groupId: 'g1', groupName: '拒识' },
      { itemId: 2, resultId: 12, sourceTaskId: 1, sourceTaskName: '任务A', sourceCaseId: 'C2', sourceCaseName: '用例2', sourceDeviceId: 7, sourceDeviceName: '设备7', sourceResultType: 'default' },
    ]),
  ];

  it('无会话缓存也按条目真实分组组织（刷新 / 直接开抽屉不落「未分组」）', () => {
    const map = resolveCartCaseOrgMap(groupsWithOrg);
    expect(map.get('C1')).toEqual({ tags: ['标签A'], groupId: 'g1', groupName: '拒识' });
    const tree = buildCartTaskView(groupsWithOrg, { caseOrgMap: map });
    expect(tree[0].children.map((n) => n.name)).toEqual(['拒识', '未分组']);
    expect(tree[0].children[1].muted).toBe(true);
    expect(hasCartCaseOrg(groupsWithOrg, map)).toBe(true);
  });

  it('条目缺字段时由会话缓存补充；条目有值时以条目为准', () => {
    const supplement = new Map<string | number, PickCaseOrgInfo>([
      ['C1', { tags: ['旧标签'], groupId: 'g0', groupName: '旧分组' }],
      ['C2', { tags: ['标签B'], groupId: 'g2', groupName: '其它' }],
    ]);
    const map = resolveCartCaseOrgMap(groupsWithOrg, supplement);
    // C1 条目有值：分组取条目值，标签取并集
    expect(map.get('C1')).toEqual({ tags: ['标签A', '旧标签'], groupId: 'g1', groupName: '拒识' });
    // C2 条目无组织字段：由会话缓存补
    expect(map.get('C2')).toEqual({ tags: ['标签B'], groupId: 'g2', groupName: '其它' });
  });

  it('条目与会话缓存全缺 → 兜底提示为真（fallback-only 才显示说明文案）', () => {
    expect(resolveCartCaseOrgMap(groups).size).toBe(0);
    expect(hasCartCaseOrg(groups, resolveCartCaseOrgMap(groups))).toBe(false);
    // 会话缓存补充命中同样算有组织数据
    expect(hasCartCaseOrg(groups, caseOrgMap)).toBe(true);
  });

  it('标签视图按条目标签分桶（四视图同一组织口径）', () => {
    const map = resolveCartCaseOrgMap(groupsWithOrg);
    const tree = buildCartTaskView(groupsWithOrg, { org: 'tag', caseOrgMap: map });
    expect(tree[0].children.map((n) => `${n.name}:${n.children.length}`)).toEqual(['标签A:1', '未设置标签:1']);
  });
});

describe('四视图共享叶 item_id 集（切换不丢勾选）', () => {
  it('任务视图全选用例卡 → 用例视图同一用例因跨任务聚合为部分选中（叶集共用）', () => {
    const taskTree = buildCartTaskView(groups, { caseOrgMap });
    const c1 = taskTree[0].children[0].children[0];
    const selected = toggleCartNode(c1, new Set<number>());
    expect([...selected].sort()).toEqual([1, 2]);

    const caseTree = buildCartCaseView(groups, { caseOrgMap });
    const sameCase = caseTree[0].children[0];
    // 用例视图下该用例含任务B 的条目 → 3 条中命中 2 条
    expect(sameCase.count).toBe(3);
    expect(cartNodeState(sameCase, selected)).toBe('indeterminate');
  });

  it('collectCartNodeKeys 覆盖所有可展开节点（全部展开）', () => {
    const tree = buildCartTaskView(groups, { caseOrgMap });
    const keys = collectCartNodeKeys(tree);
    const device = tree[0].children[0].children[0].children[0];
    const resultType = device.children[0];
    expect(keys).toContain(tree[0].key);
    expect(keys).toContain(device.key);
    // 叶前一层（result_type）不在展开集合内
    expect(keys).not.toContain(resultType.key);
  });
});

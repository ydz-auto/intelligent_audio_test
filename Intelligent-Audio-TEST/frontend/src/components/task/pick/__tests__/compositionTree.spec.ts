// -*- coding: utf-8 -*-
/**
 * 组成区纯逻辑测试（INT-1833 · 规范 18 §4）。
 *
 * 事实基线取真实库容器 580（2 个来源任务 / 5 条结果 / 5 条容器用例行 / 设备 9，
 * 已软删历史容器，关系行与源结果行保留）：任务 384 → 结果 3792/3796（failed），
 * 任务 419 → 结果 5714/5715/5716（completed）；用例行状态与结果状态存在实测冲突（5715）。
 */
import { describe, it, expect } from 'vitest';
import {
  toCompositionEntries,
  compositionCartGroups,
  compositionCaseOrgMap,
  isCompositionDegraded,
  buildCompositionView,
  buildCompositionTaskView,
  buildCompositionCaseView,
  buildCompositionDeviceView,
  buildCompositionResultTypeView,
  organizeCompositionCases,
  filterCompositionTree,
  filterCompositionEntries,
  matchesCompositionFilter,
  summarizeComposition,
  formatCompositionTime,
  compositionStatusText,
  containerMixState,
  compositionBranchCounts,
  hasCaseStatusConflict,
  isDegradedHintDismissed,
  dismissDegradedHint,
  resetDegradedHintDismissed,
  CASE_STATUS_INHERIT_TIP,
  UNKNOWN_CASE_LABEL,
  UNKNOWN_RESULT_TYPE_LABEL,
  type CompositionCaseRow,
} from '../compositionTree';
import type { PickSource } from '../../../../infrastructure/api/cherryPickApi';
import type { CartTreeNode } from '../cartTree';

/** 真实库容器 580 的 source 端点返回（关系行 created_at 与容器同值，不得当源结果时间） */
const SOURCE: PickSource = {
  taskId: 580,
  isCherryPick: true,
  total: 5,
  groups: [
    {
      sourceTaskId: 384,
      sourceTaskName: 'E2E测试任务_2026/9/21 14:09:29',
      results: [
        {
          id: 1, resultId: 3792, sourceCaseId: 'a03cc920-0000', sourceDeviceId: 9,
          // 关系行时间：不得映射为 resultCreatedAt
          createdAt: '2026-10-24T01:07:59Z',
        } as any,
        {
          id: 2, resultId: 3796, sourceCaseId: '88a1d74d-0000', sourceDeviceId: 9,
          createdAt: '2026-10-24T01:07:59Z',
        } as any,
      ],
    },
    {
      sourceTaskId: 419,
      sourceTaskName: '小艺拒识E2E测试任务_2026/10/13 17:32:59',
      results: [
        { id: 3, resultId: 5714, sourceCaseId: '14a13fa8-0000', sourceDeviceId: 9, createdAt: '2026-10-24T01:07:59Z' } as any,
        { id: 4, resultId: 5715, sourceCaseId: '0dc13869-0000', sourceDeviceId: 9, createdAt: '2026-10-24T01:07:59Z' } as any,
        { id: 5, resultId: 5716, sourceCaseId: '77ca28bc-0000', sourceDeviceId: 9, createdAt: '2026-10-24T01:07:59Z' } as any,
      ],
    },
  ],
};

/** 容器详情 cases[]（用例名 / 分组 / 标签 / 用例行状态） */
const CASES: CompositionCaseRow[] = [
  { caseId: 'a03cc920-0000', name: 'JS161 拒识用例', groupName: '拒识', tags: ['标签A'], executionStatus: 'failed', evaluationStatus: 'completed' },
  { caseId: '88a1d74d-0000', name: 'JS062 拒识用例', groupName: '拒识', tags: ['标签A'], executionStatus: 'failed', evaluationStatus: 'completed' },
  { caseId: '14a13fa8-0000', name: 'JS177 拒识用例', groupName: '拒识', tags: ['标签B'], executionStatus: 'completed', evaluationStatus: 'completed' },
  // 实测冲突：结果 5715 为 completed，用例行 0dc13869 却是 failed
  { caseId: '0dc13869-0000', name: 'JS178 拒识用例', groupName: '拒识', tags: ['标签B'], executionStatus: 'failed', evaluationStatus: 'completed' },
  { caseId: '77ca28bc-0000', name: 'JS179 拒识用例', groupName: '拒识', tags: [], executionStatus: 'completed', evaluationStatus: 'completed' },
];

const DEVICES = [{ id: 9, name: 'pura90小艺' }];
const APIS: Array<{ id: number; name: string }> = [];

const entries = () => toCompositionEntries(SOURCE, CASES, DEVICES, APIS);

const levels = (nodes: CartTreeNode[]) => nodes.map((n) => n.level);
const names = (nodes: CartTreeNode[]) => nodes.map((n) => n.name);

describe('toCompositionEntries（§4.1 条目装配）', () => {
  it('按 source.groups[].results[] 展开，保留来源任务归属', () => {
    const list = entries();
    expect(list).toHaveLength(5);
    expect(list.map((e) => e.resultId)).toEqual([3792, 3796, 5714, 5715, 5716]);
    expect(list[0].sourceTaskId).toBe(384);
    expect(list[4].sourceTaskId).toBe(419);
    expect(list[0].sourceTaskName).toContain('E2E测试任务');
  });

  it('用例名 / 分组 / 标签 / 设备名由详情 cases[] / devices[] join', () => {
    const e = entries()[0];
    expect(e.sourceCaseName).toBe('JS161 拒识用例');
    expect(e.groupName).toBe('拒识');
    expect(e.tags).toEqual(['标签A']);
    expect(e.sourceDeviceId).toBe(9);
    expect(e.sourceDeviceName).toBe('pura90小艺');
  });

  it('§4.6 降级：执行 / 评估状态取同 source_case_id 的容器用例行，并标记来源', () => {
    const e = entries()[0];
    expect(e.executionStatus).toBe('failed');
    expect(e.evaluated).toBe(true);
    expect(e.statusFromCase).toBe(true);
    expect(e.evaluationFromCase).toBe(true);
    expect(isCompositionDegraded([e])).toBe(true);
  });

  it('实测冲突：结果 5715 completed，用例行 failed → 降级期以用例行为准', () => {
    const e = entries()[3];
    expect(e.resultId).toBe(5715);
    expect(e.executionStatus).toBe('failed');
  });

  it('resultType 未落地 → null（展示「结果类型待补充」）', () => {
    expect(entries().every((e) => e.resultType === null)).toBe(true);
  });

  it('resultCreatedAt 只认 §11-8 的 result_created_at，绝不用关系行 created_at', () => {
    // 关系行 created_at 与容器同值（2026-10-24T01:07:59Z），不得出现在叶行时间位
    expect(entries().every((e) => e.resultCreatedAt === null)).toBe(true);
  });

  it('§11-8 落地后自动切真实口径（结果级字段优先于用例行）', () => {
    const landed: PickSource = {
      ...SOURCE,
      groups: [{
        sourceTaskId: 419,
        sourceTaskName: '任务419',
        results: [{
          id: 3,
          resultId: 5714,
          sourceCaseId: '14a13fa8-0000',
          sourceDeviceId: 9,
          resultType: 'final',
          executionStatus: 'completed',
          evaluated: false,
          caseName: '结果级用例名',
          resultCreatedAt: '2026-10-13T09:32:59Z',
          createdAt: '2026-10-24T01:07:59Z',
        } as any],
      }],
    };
    const [e] = toCompositionEntries(landed, CASES, DEVICES, APIS);
    expect(e.resultType).toBe('final');
    expect(e.executionStatus).toBe('completed');
    expect(e.evaluated).toBe(false);
    expect(e.sourceCaseName).toBe('结果级用例名');
    expect(e.resultCreatedAt).toBe('2026-10-13T09:32:59Z');
    expect(e.statusFromCase).toBe(false);
    expect(e.evaluationFromCase).toBe(false);
  });

  it('详情缺用例行：状态 null、评估 null（未知，不显示徽章）、用例名 null', () => {
    const unknownSource: PickSource = {
      taskId: 503,
      isCherryPick: true,
      total: 1,
      groups: [{
        sourceTaskId: 401,
        sourceTaskName: '任务401',
        results: [{ id: 1, resultId: 3837, sourceCaseId: 'deleted-case', sourceDeviceId: 9 } as any],
      }],
    };
    const [e] = toCompositionEntries(unknownSource, [], [], []);
    expect(e.executionStatus).toBeNull();
    expect(e.evaluated).toBeNull();
    expect(e.sourceCaseName).toBeNull();
    expect(e.sourceDeviceName).toBeNull();
    expect(e.missing).toBe(false);
  });

  it('source 为 null / 非容器 → 空条目', () => {
    expect(toCompositionEntries(null)).toEqual([]);
  });
});

describe('购物车同构映射（复用 P0 四视图的桥梁）', () => {
  it('按来源任务分组，叶 itemId = resultId', () => {
    const groups = compositionCartGroups(entries());
    expect(groups.map((g) => g.sourceTaskId)).toEqual([384, 419]);
    expect(groups[0].items.map((i) => i.itemId)).toEqual([3792, 3796]);
    expect(groups[1].items.map((i) => i.itemId)).toEqual([5714, 5715, 5716]);
  });

  it('缺名用例降级「未知用例」，不裸显 UUID', () => {
    const source: PickSource = {
      taskId: 1, isCherryPick: true, total: 1,
      groups: [{ sourceTaskId: 9, sourceTaskName: '任务9', results: [{ id: 1, resultId: 11, sourceCaseId: 'abcdef12-3456' } as any] }],
    };
    const list = toCompositionEntries(source, [], [], []);
    const [item] = compositionCartGroups(list)[0].items;
    expect(item.sourceCaseName).toBe(UNKNOWN_CASE_LABEL);
    expect(item.sourceCaseName).not.toContain('abcdef12');
    expect(UNKNOWN_CASE_LABEL).toBe('未知用例');
  });

  it('组织字段映射：同用例跨条目标签并集、分组取首个非空值（group_id 以组名为键）', () => {
    const map = compositionCaseOrgMap(entries());
    expect(map.get('a03cc920-0000')).toEqual({ tags: ['标签A'], groupId: '拒识', groupName: '拒识' });
  });
});

describe('四视图层级（§3.2，复用 P0 buildCartView，任务层恒渲染）', () => {
  it('任务视图：任务 → 用例层组织 → 用例卡 → 设备/API → result_type → 叶', () => {
    const roots = buildCompositionTaskView(entries());
    expect(levels(roots)).toEqual(['task', 'task']);
    expect(names(roots)[0]).toContain('E2E测试任务');
    const task = roots[0];
    expect(levels(task.children)).toEqual(['org']);
    const bucket = task.children[0];
    expect(bucket.name).toBe('拒识');
    expect(levels(bucket.children)).toEqual(['case', 'case']);
    const caseNode = bucket.children[0];
    expect(levels(caseNode.children)).toEqual(['device']);
    expect(names(caseNode.children)).toEqual(['pura90小艺']);
    const rt = caseNode.children[0].children;
    expect(levels(rt)).toEqual(['resultType']);
    expect(rt[0].name).toBe(UNKNOWN_RESULT_TYPE_LABEL);
  });

  it('用例视图：用例层组织 → 用例卡 → 设备/API → result_type → 任务 → 叶', () => {
    const roots = buildCompositionCaseView(entries());
    expect(levels(roots)).toEqual(['org']);
    const caseNode = roots[0].children[0];
    expect(caseNode.level).toBe('case');
    const device = caseNode.children[0];
    expect(device.level).toBe('device');
    const rt = device.children[0];
    expect(rt.level).toBe('resultType');
    const taskLayer = rt.children;
    expect(levels(taskLayer)).toEqual(['task']);
    expect(taskLayer[0].itemIds.length).toBeGreaterThan(0);
  });

  it('设备视图：设备/API → result_type → 用例层组织 → 用例卡 → 任务 → 叶', () => {
    const roots = buildCompositionDeviceView(entries());
    expect(levels(roots)).toEqual(['device']);
    const rt = roots[0].children[0];
    expect(rt.level).toBe('resultType');
    expect(levels(rt.children)).toEqual(['org']);
    const caseNode = rt.children[0].children[0];
    expect(caseNode.level).toBe('case');
    expect(levels(caseNode.children)).toEqual(['task']);
  });

  it('结果类型视图：result_type → 设备/API → 用例层组织 → 用例卡 → 任务 → 叶', () => {
    const roots = buildCompositionResultTypeView(entries());
    expect(levels(roots)).toEqual(['resultType']);
    expect(names(roots)).toEqual([UNKNOWN_RESULT_TYPE_LABEL]);
    const device = roots[0].children[0];
    expect(device.level).toBe('device');
    expect(levels(device.children)).toEqual(['org']);
    const caseNode = device.children[0].children[0];
    expect(caseNode.level).toBe('case');
    expect(levels(caseNode.children)).toEqual(['task']);
  });

  it('单来源容器同样恒渲染任务层（§1.3）', () => {
    const single: PickSource = {
      taskId: 503, isCherryPick: true, total: 1,
      groups: [{ sourceTaskId: 401, sourceTaskName: '单来源任务', results: [{ id: 1, resultId: 3837, sourceCaseId: 'x1' } as any] }],
    };
    const list = toCompositionEntries(single, [{ caseId: 'x1', name: '用例X', groupName: '组X', tags: [] }], [], []);
    const taskView = buildCompositionTaskView(list);
    expect(levels(taskView)).toEqual(['task']);
    const caseView = buildCompositionCaseView(list);
    const rt = caseView[0].children[0].children[0].children[0];
    expect(levels(rt.children)).toEqual(['task']);
    expect(rt.children[0].name).toBe('单来源任务');
  });

  it('视图分发与单个 builder 等价', () => {
    const list = entries();
    expect(buildCompositionView('task', list)).toEqual(buildCompositionTaskView(list));
    expect(buildCompositionView('resultType', list)).toEqual(buildCompositionResultTypeView(list));
  });
});

describe('organizeCompositionCases（分组 / 标签 × 平铺 / 交叉，与 React 同口径）', () => {
  const list = entries();

  it('分组视图 · 平铺：按 groupName 聚合，组内为命中条目', () => {
    const groups = organizeCompositionCases(list, 'group', 'flat');
    expect(groups.map((g) => g.label)).toEqual(['拒识']);
    expect(groups[0].entries).toHaveLength(5);
    expect(groups[0].subGroups).toEqual([]);
  });

  it('分组视图 · 交叉：组内再按标签分子组（空组不下发）', () => {
    const groups = organizeCompositionCases(list, 'group', 'byTag');
    expect(groups[0].subGroups.map((s) => s.label).sort()).toEqual(['未设置标签', '标签A', '标签B'].sort());
    expect(groups[0].subGroups.every((s) => s.entries.length > 0)).toBe(true);
  });

  it('标签视图 · 平铺：按标签聚合，多标签条目在各桶各呈现一次，无标签落兜底桶', () => {
    const groups = organizeCompositionCases(list, 'tag', 'flat');
    const labels = groups.map((g) => g.label);
    expect(labels).toContain('标签A');
    expect(labels).toContain('标签B');
    expect(labels).toContain('未设置标签');
    const unlabeled = groups.find((g) => g.label === '未设置标签');
    expect(unlabeled?.muted).toBe(true);
    expect(unlabeled?.entries.map((e) => e.resultId)).toEqual([5716]);
  });

  it('标签视图 · 交叉：标签桶内再按分组分子组', () => {
    const groups = organizeCompositionCases(list, 'tag', 'byGroup');
    const tagA = groups.find((g) => g.label === '标签A');
    expect(tagA?.subGroups.map((s) => s.label)).toEqual(['拒识']);
    expect(tagA?.subGroups[0].entries).toHaveLength(2);
  });

  it('无组织字段：单兜底桶（组织控件可保留兜底提示）', () => {
    const noOrg = list.map((e) => ({ ...e, groupName: null, tags: [] }));
    const groups = organizeCompositionCases(noOrg, 'group', 'flat');
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe('未分组');
    expect(groups[0].muted).toBe(true);
  });
});

describe('筛选（§5：命中叶保留 + 祖先保留 + 计数按命中集重算）', () => {
  const list = entries();

  it('执行状态筛选命中判定', () => {
    const failed = filterCompositionEntries(list, 'failed');
    expect(failed.map((e) => e.resultId)).toEqual([3792, 3796, 5715]);
    expect(matchesCompositionFilter(list[0], 'completed')).toBe(false);
    expect(matchesCompositionFilter(list[0], 'failed')).toBe(true);
    expect(matchesCompositionFilter(list[0], 'all', 'evaluated')).toBe(true);
    expect(matchesCompositionFilter({ ...list[0], evaluated: false }, 'all', 'unevaluated')).toBe(true);
    expect(matchesCompositionFilter({ ...list[1], evaluated: false }, 'all', 'evaluated')).toBe(false);
  });

  it('树筛选：不命中的叶与空祖先一并移除，保留节点计数重算', () => {
    const roots = buildCompositionTaskView(list);
    const map = new Map(list.map((e) => [e.resultId, e] as const));
    const filtered = filterCompositionTree(roots, 'failed', 'all', map);
    expect(levels(filtered)).toEqual(['task', 'task']);
    // 任务 384 两条都 failed；任务 419 仅 5715 failed
    expect(filtered[0].children[0].children.flatMap((c) => c.itemIds).sort()).toEqual([3792, 3796]);
    const task419 = filtered[1];
    expect(task419.count).toBe(1);
    const device = task419.children[0].children[0].children[0];
    expect(device.level).toBe('device');
    expect(device.itemIds).toEqual([5715]);
  });

  it('筛选后 0 条 → 空树（工具行空态）', () => {
    const roots = buildCompositionTaskView(list);
    const map = new Map(list.map((e) => [e.resultId, e] as const));
    expect(filterCompositionTree(roots, 'stopped', 'all', map)).toEqual([]);
  });

  it('筛选不改层级结构（节点 key 稳定，展开态可保持）', () => {
    const roots = buildCompositionTaskView(list);
    const map = new Map(list.map((e) => [e.resultId, e] as const));
    const filtered = filterCompositionTree(roots, 'failed', 'all', map);
    expect(filtered[0].key).toBe(roots[0].key);
    expect(filtered[0].children[0].key).toBe(roots[0].children[0].key);
  });
});

describe('失效筛选（§7 顶部 Alert「只看失效」——同一套 filterCompositionTree 语义）', () => {
  /** 3796 / 5715 两条源结果已删除（missing=true） */
  const list = entries().map((e) =>
    e.resultId === 3796 || e.resultId === 5715 ? { ...e, missing: true } : e);

  it('条目级：缺失维度只保留 missing=true 的叶', () => {
    expect(filterCompositionEntries(list, 'all', 'all', 'missing').map((e) => e.resultId))
      .toEqual([3796, 5715]);
    expect(matchesCompositionFilter(list[0], 'all', 'all', 'missing')).toBe(false);
    const missingEntry = list.find((e) => e.resultId === 3796)!;
    expect(matchesCompositionFilter(missingEntry, 'all', 'all', 'missing')).toBe(true);
    // 默认维度 = all（不改变既有调用语义）
    expect(filterCompositionEntries(list)).toHaveLength(5);
  });

  it('树筛选：「只看失效」保留祖先并按命中集重算计数，形态不变', () => {
    const roots = buildCompositionTaskView(list);
    const map = new Map(list.map((e) => [e.resultId, e] as const));
    const filtered = filterCompositionTree(roots, 'all', 'all', map, 'missing');
    expect(levels(filtered)).toEqual(['task', 'task']);
    expect(filtered[0].count).toBe(1);
    expect(filtered[0].itemIds).toEqual([3796]);
    expect(filtered[1].count).toBe(1);
    expect(filtered[1].itemIds).toEqual([5715]);
    // 节点 key 与原树一致（展开态可保持）
    expect(filtered.map((n) => n.key)).toEqual(roots.map((n) => n.key));
  });

  it('「只看失效」与执行 / 评估筛选叠加（同一套语义，不另造筛选）', () => {
    const roots = buildCompositionTaskView(list);
    const map = new Map(list.map((e) => [e.resultId, e] as const));
    const filtered = filterCompositionTree(roots, 'failed', 'all', map, 'missing');
    // 失叶片 3796（failed）/ 5715（用例行降级 failed）
    expect(filtered.flatMap((n) => n.itemIds).sort()).toEqual([3796, 5715]);
    const completedOnly = filterCompositionTree(roots, 'completed', 'all', map, 'missing');
    expect(completedOnly).toEqual([]);
  });

  it('摘要按失效维度统计（顶部 Alert 的 k 与筛选结果同源）', () => {
    expect(summarizeComposition(list, 'all', 'all', 'missing').missing).toBe(2);
    expect(summarizeComposition(list).missing).toBe(2);
    expect(summarizeComposition(list, 'all', 'all', 'missing').total).toBe(2);
  });
});

describe('摘要 / 展示辅助', () => {
  it('summarizeComposition：全部 / 失败 / 未评估 / 失效 / 任务数 / 用例数 / 设备数', () => {
    const withMissing = entries().map((e, i) => (i === 1 ? { ...e, missing: true, evaluated: false } : e));
    const summary = summarizeComposition(withMissing);
    expect(summary).toEqual({
      total: 5,
      failed: 3,
      unevaluated: 1,
      missing: 1,
      taskCount: 2,
      caseCount: 5,
      deviceCount: 1,
    });
  });

  it('summarizeComposition 支持按筛选后条目统计', () => {
    const summary = summarizeComposition(entries(), 'failed', 'all');
    expect(summary.total).toBe(3);
    expect(summary.failed).toBe(3);
    expect(summary.taskCount).toBe(2);
  });

  it('formatCompositionTime 输出 mono「YYYY-MM-DD HH:mm」，非法值返回空串', () => {
    expect(formatCompositionTime('2026-10-13T09:32:59Z')).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
    expect(formatCompositionTime(null)).toBe('');
    expect(formatCompositionTime('')).toBe('');
    expect(formatCompositionTime('not-a-date')).toBe('');
  });

  it('compositionStatusText 文案（§5 已完成 / 已失败 / 已停止）', () => {
    expect(compositionStatusText('completed')).toBe('已完成');
    expect(compositionStatusText('failed')).toBe('已失败');
    expect(compositionStatusText('stopped')).toBe('已停止');
    expect(compositionStatusText(null)).toBe('未知状态');
  });
});

/**
 * INT-1836 · 规范 18 §2.1/§5：部分失败 / 未评估呈现映射。
 *
 * - `containerMixState`：列表执行状态纯前端展示映射（后端字符串仍是 failed）
 * - `compositionBranchCounts`：分支计数「{n} 条 · 失败 {f} · 失效 {k}」
 * - `hasCaseStatusConflict`：用例卡一致性（用例继承状态 vs 叶状态）
 */
describe('部分失败呈现（§5，INT-1836）', () => {
  it('containerMixState：0 < failed < caseCount → partial；== caseCount → all；其余 none', () => {
    expect(containerMixState(3, 5)).toBe('partial');
    expect(containerMixState(5, 5)).toBe('all');
    expect(containerMixState(6, 5)).toBe('all');
    expect(containerMixState(0, 5)).toBe('none');
    expect(containerMixState(null, 5)).toBe('none');
    expect(containerMixState(3, null)).toBe('none');
    expect(containerMixState(undefined, undefined)).toBe('none');
    expect(containerMixState(3, 0)).toBe('none');
  });

  it('compositionBranchCounts：按节点下过滤后叶统计失败 / 失效，去重不重复计', () => {
    const list = entries();
    const map = new Map(list.map((e) => [e.resultId, e]));
    // 全量：3792/3796 执行 failed（降级取用例行），5714/5715/5716 completed
    expect(compositionBranchCounts([3792, 3796, 5714], map)).toEqual({ failed: 2, missing: 0 });
    // 多标签同一叶重复出现时只计一次
    expect(compositionBranchCounts([3792, 3792, 3796], map)).toEqual({ failed: 2, missing: 0 });
    // 未知 id 跳过
    expect(compositionBranchCounts([999999], map)).toEqual({ failed: 0, missing: 0 });
  });

  it('compositionBranchCounts：失效叶计入 missing（§7 失效标记）', () => {
    const list = entries();
    list[0] = { ...list[0], missing: true };
    const map = new Map(list.map((e) => [e.resultId, e]));
    expect(compositionBranchCounts([3792, 3796], map)).toEqual({ failed: 2, missing: 1 });
  });

  it('hasCaseStatusConflict：降级期叶状态取自用例行 → 恒等，不误报', () => {
    const list = entries();
    const map = new Map(list.map((e) => [e.resultId, e]));
    // 5715 的用例行 0dc13869 为 failed，降级期叶也取 failed
    expect(hasCaseStatusConflict([5715], map)).toBe(false);
  });

  it('hasCaseStatusConflict：§11-8 结果级状态与用例行继承状态不一致 → 冲突（实测 5715）', () => {
    const list = toCompositionEntries(
      {
        ...SOURCE,
        groups: [{
          sourceTaskId: 419,
          sourceTaskName: '小艺拒识E2E测试任务',
          results: [{
            id: 4, resultId: 5715, sourceCaseId: '0dc13869-0000', sourceDeviceId: 9,
            // §11-8 结果级字段落地：源结果为 completed
            executionStatus: 'completed', evaluated: true,
          } as any],
        }],
      },
      CASES,
      DEVICES,
      APIS,
    );
    const map = new Map(list.map((e) => [e.resultId, e]));
    expect(list[0].caseExecutionStatus).toBe('failed');
    expect(list[0].executionStatus).toBe('completed');
    expect(hasCaseStatusConflict([5715], map)).toBe(true);
    expect(CASE_STATUS_INHERIT_TIP).toBe('用例状态继承自来源任务；结果状态以叶行为准');
  });

  it('hasCaseStatusConflict：评估侧不一致（用例行已完成评估，所选结果 evaluated=false）→ 冲突', () => {
    const list = toCompositionEntries(
      {
        ...SOURCE,
        groups: [{
          sourceTaskId: 384,
          sourceTaskName: 'E2E测试任务',
          results: [{
            id: 1, resultId: 3792, sourceCaseId: 'a03cc920-0000', sourceDeviceId: 9,
            // 源结果 failed 且未评估；用例行 failed（执行一致）+ 评估 completed（评估冲突）
            executionStatus: 'failed', evaluated: false,
          } as any],
        }],
      },
      CASES,
      DEVICES,
      APIS,
    );
    const map = new Map(list.map((e) => [e.resultId, e]));
    expect(list[0].caseEvaluationStatus).toBe('completed');
    expect(list[0].evaluated).toBe(false);
    expect(hasCaseStatusConflict([3792], map)).toBe(true);
  });

  it('hasCaseStatusConflict：叶状态未知（null）或无用例行 → 不判定冲突', () => {
    const list = entries();
    const noCaseRow = { ...list[0], caseExecutionStatus: null, executionStatus: null };
    const map = new Map<number, (typeof list)[number]>([[1, noCaseRow]]);
    expect(hasCaseStatusConflict([1], map)).toBe(false);
    expect(hasCaseStatusConflict([], map)).toBe(false);
  });

  it('降级期提示判定：执行降级 / 评估降级 / 都未降级（任一降级即显示，§4.6）', () => {
    const base = entries()[0];
    expect(isCompositionDegraded([{ ...base, statusFromCase: true, evaluationFromCase: false }])).toBe(true);
    expect(isCompositionDegraded([{ ...base, statusFromCase: false, evaluationFromCase: true }])).toBe(true);
    expect(isCompositionDegraded([{ ...base, statusFromCase: false, evaluationFromCase: false }])).toBe(false);
  });

  it('降级期提示关闭态是会话级（模块状态，组件重挂仍保持）', () => {
    expect(isDegradedHintDismissed()).toBe(false);
    dismissDegradedHint();
    expect(isDegradedHintDismissed()).toBe(true);
    resetDegradedHintDismissed();
    expect(isDegradedHintDismissed()).toBe(false);
  });
});

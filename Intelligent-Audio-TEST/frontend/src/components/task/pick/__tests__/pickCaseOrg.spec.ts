// -*- coding: utf-8 -*-
/**
 * 用例视图组织维度纯逻辑测试（18_挑选合并交互重设计.md §3.8.3，INT-1110 返工 P1）。
 *
 * 覆盖：分组视图（按用例分组聚合 +「未分组」兜底）／标签视图（按标签聚合 +「未设置标签」兜底）；
 * §11-7 扩展点 caseOrgMap 注入后按真实分组/标签聚合；组织纯派生不触碰选中集（勾选联动解耦）。
 */
import { describe, it, expect } from 'vitest';
import {
  buildPickCaseViewTree,
  buildPickCaseOrgBuckets,
  collectLeafResultIds,
  type PickCaseOrgInfo,
} from '../pickTree';
import { UNTAGGED_BUCKET_KEY, UNGROUPED_BUCKET_KEY } from '../../../../domain/lib/subViewAggregation';
import type { PickCandidate } from '../../../../infrastructure/api/cherryPickApi';

function cand(partial: Partial<PickCandidate> & { resultId: number; taskId: number; caseId: string }): PickCandidate {
  return {
    taskName: `任务${partial.taskId}`,
    taskStatus: 'completed',
    caseName: `用例${partial.caseId}`,
    resultType: 'default',
    executionStatus: 'completed',
    evaluated: true,
    ...partial,
  };
}

describe('buildPickCaseOrgBuckets（用例视图组织维度，INT-1110 返工 P1）', () => {
  const rows = () => [
    cand({ resultId: 1, taskId: 1, caseId: 'C1', deviceId: 7, resultType: 'real-time' }),
    cand({ resultId: 2, taskId: 1, caseId: 'C1', deviceId: 8, resultType: 'final' }),
    cand({ resultId: 3, taskId: 2, caseId: 'C2', deviceId: 9, resultType: 'default' }),
  ];

  it('候选未返分组字段 → 分组视图全落「未分组」单兜底桶（组织控件仍生效）', () => {
    const roots = buildPickCaseViewTree(rows());
    const buckets = buildPickCaseOrgBuckets(roots, 'group');
    expect(buckets).toHaveLength(1);
    expect(buckets[0].key).toBe(UNGROUPED_BUCKET_KEY);
    expect(buckets[0].label).toBe('未分组');
    // 桶内容 = 全部用例级分支（C1 / C2）
    expect(buckets[0].cases.map((c) => c.branch.id)).toEqual(['C1', 'C2']);
    // 分支保真：用例根仍可驱动 R6 勾选（组织不改变树结构）
    const c1 = buckets[0].cases.find((c) => c.branch.id === 'C1')!.branch;
    expect(c1.level).toBe('case');
    expect(c1.children.length).toBeGreaterThan(0);
  });

  it('候选未返标签字段 → 标签视图全落「未设置标签」单兜底桶', () => {
    const roots = buildPickCaseViewTree(rows());
    const buckets = buildPickCaseOrgBuckets(roots, 'tag');
    expect(buckets).toHaveLength(1);
    expect(buckets[0].key).toBe(UNTAGGED_BUCKET_KEY);
    expect(buckets[0].label).toBe('未设置标签');
    expect(buckets[0].cases).toHaveLength(2);
  });

  it('§11-7 扩展点：caseOrgMap 注入分组字段 → 分组视图按分组聚合，无分组用例入「未分组」兜底', () => {
    const roots = buildPickCaseViewTree(rows());
    const map = new Map<string | number, PickCaseOrgInfo>([
      ['C1', { groupId: 'g1', groupName: '核心链路' }],
      // C2 未注入 → 兜底
    ]);
    const buckets = buildPickCaseOrgBuckets(roots, 'group', map);
    expect(buckets.map((b) => b.label)).toEqual(['核心链路', '未分组']);
    expect(buckets[0].cases.map((c) => c.branch.id)).toEqual(['C1']);
    expect(buckets[1].key).toBe(UNGROUPED_BUCKET_KEY);
    expect(buckets[1].cases.map((c) => c.branch.id)).toEqual(['C2']);
  });

  it('§11-7 扩展点：caseOrgMap 注入标签字段 → 标签视图按标签聚合（多标签用例多次呈现），无标签入兜底', () => {
    const roots = buildPickCaseViewTree(rows());
    const map = new Map<string | number, PickCaseOrgInfo>([
      ['C1', { tags: ['会议', '长文本'] }],
    ]);
    const buckets = buildPickCaseOrgBuckets(roots, 'tag', map);
    const labels = buckets.map((b) => b.label);
    // 多标签用例在命中的每个标签子组各呈现一次；无标签用例入「未设置标签」兜底（末尾）
    expect(labels).toContain('会议');
    expect(labels).toContain('长文本');
    expect(labels).toContain('未设置标签');
    expect(buckets[buckets.length - 1].key).toBe(UNTAGGED_BUCKET_KEY);
    const meeting = buckets.find((b) => b.label === '会议')!;
    expect(meeting.cases.map((c) => c.branch.id)).toEqual(['C1']);
    const untagged = buckets.find((b) => b.key === UNTAGGED_BUCKET_KEY)!;
    expect(untagged.cases.map((c) => c.branch.id)).toEqual(['C2']);
  });

  it('组织只影响视觉分组：构建组织桶不改树、不触碰选中集（纯派生，勾选联动解耦）', () => {
    const roots = buildPickCaseViewTree(rows());
    const before = collectLeafResultIds(roots).sort((a, b) => a - b);
    buildPickCaseOrgBuckets(roots, 'group');
    buildPickCaseOrgBuckets(roots, 'tag');
    const after = collectLeafResultIds(roots).sort((a, b) => a - b);
    expect(after).toEqual(before);
  });
});

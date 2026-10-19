// -*- coding: utf-8 -*-
/**
 * 挑选树纯逻辑测试（INT-577 §3 联动规则 R1-R10）。
 *
 * 覆盖：四级树构建（任务→用例→设备/API→result_type）；节点三态派生；
 * R1/R2 父子联动；R4 device 清容器；R5 result_type 仅清叶；R9 全选/反选。
 */
import { describe, it, expect } from 'vitest';
import {
  buildPickTree, buildPickCaseViewTree, nodeState, toggleNode, selectAll, invertSelection, collectLeafResultIds,
} from '../pickTree';
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

describe('buildPickTree（四级分组）', () => {
  it('任务→用例→设备→result_type→叶 四级分组', () => {
    const rows = [
      cand({ resultId: 1, taskId: 1, caseId: 'C1', deviceId: 7, resultType: 'real-time' }),
      cand({ resultId: 2, taskId: 1, caseId: 'C1', deviceId: 7, resultType: 'final' }),
      cand({ resultId: 3, taskId: 1, caseId: 'C2', deviceId: 8, resultType: 'default' }),
    ];
    const tree = buildPickTree(rows);
    expect(tree).toHaveLength(1);
    const task = tree[0];
    expect(task.level).toBe('task');
    expect(task.count).toBe(3);
    expect(task.children).toHaveLength(2); // C1 / C2
    const c1 = task.children[0];
    expect(c1.name).toBe('用例C1');
    expect(c1.children).toHaveLength(1); // 设备 7
    expect(c1.children[0].children).toHaveLength(2); // real-time / final
    expect(c1.children[0].children.map((n) => n.name)).toEqual(['real-time', 'final']);
    expect(c1.children[0].children[0].resultIds).toEqual([1]);
    expect(c1.children[0].children[1].resultIds).toEqual([2]);
    const c2 = task.children[1];
    expect(c2.children[0].name).toBe('设备 8');
  });

  it('API 型结果（无 device_id）落到 API 节点（kind=api）', () => {
    const rows = [cand({ resultId: 1, taskId: 1, caseId: 'C1', apiId: 101, resultType: 'streaming' })];
    const tree = buildPickTree(rows);
    const dim = tree[0].children[0].children[0];
    expect(dim.kind).toBe('api');
    expect(dim.name).toBe('API 101');
  });

  it('result_type 缺省折叠「结果类型待补充」（§3.7.1 PENDING 口径）', () => {
    const rows = [cand({ resultId: 1, taskId: 1, caseId: 'C1', deviceId: 7, resultType: null })];
    const tree = buildPickTree(rows);
    expect(tree[0].children[0].children[0].children[0].name).toBe('结果类型待补充');
    expect(tree[0].children[0].children[0].children[0].id).toBe('default');
  });
});

describe('nodeState（三态派生）', () => {
  const rows = [
    cand({ resultId: 1, taskId: 1, caseId: 'C1', deviceId: 7, resultType: 'real-time' }),
    cand({ resultId: 2, taskId: 1, caseId: 'C1', deviceId: 7, resultType: 'final' }),
  ];
  const tree = buildPickTree(rows);
  const task = tree[0];
  const rtReal = task.children[0].children[0].children[0];
  const rtFinal = task.children[0].children[0].children[1];

  it('空选 → unchecked；全选 → checked；部分 → indeterminate', () => {
    expect(nodeState(task, new Set())).toBe('unchecked');
    expect(nodeState(task, new Set([1, 2]))).toBe('checked');
    expect(nodeState(task, new Set([1]))).toBe('indeterminate');
    expect(nodeState(rtReal, new Set([1]))).toBe('checked');
    expect(nodeState(rtReal, new Set())).toBe('unchecked');
    expect(nodeState(rtFinal, new Set([1]))).toBe('unchecked');
  });
});

describe('联动规则 R1/R2（父子勾选）', () => {
  const rows = [
    cand({ resultId: 1, taskId: 1, caseId: 'C1', deviceId: 7, resultType: 'real-time' }),
    cand({ resultId: 2, taskId: 1, caseId: 'C1', deviceId: 7, resultType: 'final' }),
    cand({ resultId: 3, taskId: 2, caseId: 'C2', deviceId: 8, resultType: 'default' }),
  ];
  const tree = buildPickTree(rows);
  const task1 = tree[0];
  const task2 = tree[1];

  it('R1 勾选任务级 = 整任务全部叶；R8 跨任务独立', () => {
    const sel = toggleNode(task1, new Set());
    expect(sel).toEqual(new Set([1, 2]));
    expect(nodeState(task1, sel)).toBe('checked');
    // 任务 2 未受影响
    expect(nodeState(task2, sel)).toBe('unchecked');
  });

  it('R2 取消父级清空其全部子孙', () => {
    const sel = toggleNode(task1, new Set()); // 勾选任务级 → 全选
    expect(sel).toEqual(new Set([1, 2]));
    const cleared = toggleNode(task1, sel); // 再次取消 → 清空
    expect(cleared).toEqual(new Set());
  });

  it('R3 子级全选后父级转全选；部分选中父级 indeterminate', () => {
    const sel = toggleNode(tree[0].children[0].children[0].children[0], new Set()); // 勾 real-time
    expect(nodeState(task1, sel)).toBe('indeterminate');
    const sel2 = toggleNode(tree[0].children[0].children[0].children[1], sel); // 勾 final
    expect(nodeState(task1, sel2)).toBe('checked');
  });
});

describe('联动规则 R4/R5（device 与 result_type 层级差异）', () => {
  const rows = [
    cand({ resultId: 1, taskId: 1, caseId: 'C1', deviceId: 7, resultType: 'real-time' }),
    cand({ resultId: 2, taskId: 1, caseId: 'C1', deviceId: 7, resultType: 'final' }),
  ];
  const tree = buildPickTree(rows);
  const device = tree[0].children[0].children[0];
  const rtReal = device.children[0];
  const rtFinal = device.children[1];

  it('R5 取消 result_type 仅清其下叶，device 保持部分选中', () => {
    const sel = toggleNode(device, new Set()); // 全选 device
    expect(nodeState(device, sel)).toBe('checked');
    const afterRtClear = toggleNode(rtReal, sel); // 取消 real-time
    expect(afterRtClear).toEqual(new Set([2]));
    expect(nodeState(rtFinal, afterRtClear)).toBe('checked');
    expect(nodeState(device, afterRtClear)).toBe('indeterminate'); // device 保持部分
  });

  it('R4 取消 device 清其下 result_type 与全部叶（不残留）', () => {
    const sel = toggleNode(device, new Set()); // 全选 device
    const afterDeviceClear = toggleNode(device, sel); // 取消 device
    expect(afterDeviceClear).toEqual(new Set());
    expect(nodeState(rtReal, afterDeviceClear)).toBe('unchecked');
    expect(nodeState(rtFinal, afterDeviceClear)).toBe('unchecked');
  });
});

describe('R9 全选当前筛选 / 反选', () => {
  const rows = [
    cand({ resultId: 1, taskId: 1, caseId: 'C1', deviceId: 7 }),
    cand({ resultId: 2, taskId: 1, caseId: 'C1', deviceId: 7 }),
    cand({ resultId: 3, taskId: 2, caseId: 'C2', deviceId: 8 }),
  ];
  const tree = buildPickTree(rows);
  const leaves = collectLeafResultIds(tree);

  it('collectLeafResultIds 汇总全部叶', () => {
    expect(leaves.sort()).toEqual([1, 2, 3]);
  });

  it('全选 = 加入全部命中叶（保留跨页已选）', () => {
    const sel = selectAll([2, 3], new Set([1]));
    expect(sel).toEqual(new Set([1, 2, 3]));
  });

  it('反选 = 仅对给定叶取反（保留其余已选）', () => {
    const sel = invertSelection([1, 2], new Set([2, 3]));
    expect(sel).toEqual(new Set([1, 3]));
  });
});

describe('buildPickCaseViewTree（用例视角，§3.6 裁定③ / §3.7.3）', () => {
  it('跨任务按用例聚合：用例 → 来源任务列表 → 设备 → result_type → 叶', () => {
    const rows = [
      cand({ resultId: 1, taskId: 1, caseId: 'C1', deviceId: 7, resultType: 'real-time', algorithmType: 'asr' }),
      cand({ resultId: 2, taskId: 1, caseId: 'C1', deviceId: 7, resultType: 'final' }),
      cand({ resultId: 3, taskId: 2, caseId: 'C1', deviceId: 9, resultType: 'default' }),
      cand({ resultId: 4, taskId: 1, caseId: 'C2', deviceId: 8, resultType: 'streaming' }),
    ];
    const tree = buildPickCaseViewTree(rows);
    expect(tree).toHaveLength(2); // C1 / C2 根
    const c1 = tree.find((n) => n.id === 'C1')!;
    expect(c1.level).toBe('case');
    expect(c1.count).toBe(3);
    expect(c1.algorithmType).toBe('asr');
    expect(c1.children).toHaveLength(2); // 任务 1 / 任务 2
    const task1 = c1.children.find((n) => n.id === 1)!;
    expect(task1.level).toBe('task');
    expect(task1.children).toHaveLength(1); // 设备 7
    expect(task1.children[0].children.map((n) => n.name)).toEqual(['real-time', 'final']);
    const task2 = c1.children.find((n) => n.id === 2)!;
    expect(task2.children[0].id).toBe(9);
  });

  it('用例视角勾选联动复用 R1-R7（取消任务级仅清该任务结果行，用例保持部分）', () => {
    const rows = [
      cand({ resultId: 1, taskId: 1, caseId: 'C1', deviceId: 7, resultType: 'real-time' }),
      cand({ resultId: 2, taskId: 2, caseId: 'C1', deviceId: 9, resultType: 'default' }),
    ];
    const tree = buildPickCaseViewTree(rows);
    const c1 = tree[0];
    const task1 = c1.children[0];
    // R7 语义：勾选用例根 = 跨任务全部结果
    const sel = toggleNode(c1, new Set());
    expect(sel).toEqual(new Set([1, 2]));
    // 取消任务 1 → 仅清该任务下结果行，用例保持部分选中
    const after = toggleNode(task1, sel);
    expect(after).toEqual(new Set([2]));
    expect(nodeState(c1, after)).toBe('indeterminate');
    expect(nodeState(task1, after)).toBe('unchecked');
  });
});

// -*- coding: utf-8 -*-
/**
 * 挑选树纯逻辑测试（INT-577 §3 联动规则 R1-R10）。
 *
 * 覆盖：四级树构建（任务→用例→设备/API→result_type）；节点三态派生；
 * R1/R2 父子联动；R4 device 清容器；R5 result_type 仅清叶；R9 全选/反选。
 */
import { describe, it, expect } from 'vitest';
import {
  buildPickTree, buildPickCaseViewTree, buildPickDeviceViewTree, buildPickResultTypeViewTree,
  nodeState, toggleNode, selectAll, invertSelection, collectLeafResultIds,
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

describe('buildPickCaseViewTree（INT-1034 §3.8.3 用例视图，任务维度由阶段 1 承载）', () => {
  it('用例 → 设备/API → result_type → 叶（树内无任务级分支）', () => {
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
    // 用例下直挂设备层（无任务级）
    expect(c1.children).toHaveLength(2); // 设备 7 / 设备 9
    expect(c1.children.map((n) => n.level)).toEqual(['device', 'device']);
    const d7 = c1.children.find((n) => n.id === 7)!;
    expect(d7.children.map((n) => n.name)).toEqual(['real-time', 'final']);
    const d9 = c1.children.find((n) => n.id === 9)!;
    expect(d9.children[0].id).toBe('default');
  });

  it('用例级勾选 R6 语义：勾选用例根 = 跨设备/结果类型全部结果；取消设备仅清该设备', () => {
    const rows = [
      cand({ resultId: 1, taskId: 1, caseId: 'C1', deviceId: 7, resultType: 'real-time' }),
      cand({ resultId: 2, taskId: 2, caseId: 'C1', deviceId: 9, resultType: 'default' }),
    ];
    const tree = buildPickCaseViewTree(rows);
    const c1 = tree[0];
    const d7 = c1.children.find((n) => n.id === 7)!;
    // 勾选用例根 = 全部结果
    const sel = toggleNode(c1, new Set());
    expect(sel).toEqual(new Set([1, 2]));
    expect(nodeState(c1, sel)).toBe('checked');
    // 取消设备 7 → 仅清该设备下结果行，用例保持部分选中
    const after = toggleNode(d7, sel);
    expect(after).toEqual(new Set([2]));
    expect(nodeState(c1, after)).toBe('indeterminate');
    expect(nodeState(d7, after)).toBe('unchecked');
  });
});

describe('buildPickDeviceViewTree（INT-1034 §3.8.3 设备视图）', () => {
  it('设备/API → result_type → 用例 → 叶（三视图同源，叶 result_id 与用例视图一致）', () => {
    const rows = [
      cand({ resultId: 1, taskId: 1, caseId: 'C1', deviceId: 7, resultType: 'real-time' }),
      cand({ resultId: 2, taskId: 2, caseId: 'C1', deviceId: 7, resultType: 'real-time' }),
      cand({ resultId: 3, taskId: 1, caseId: 'C2', deviceId: 8, resultType: 'final' }),
    ];
    const tree = buildPickDeviceViewTree(rows);
    expect(tree).toHaveLength(2); // 设备 7 / 设备 8
    const d7 = tree.find((n) => n.id === 7)!;
    expect(d7.level).toBe('device');
    expect(d7.count).toBe(2);
    expect(d7.children).toHaveLength(1); // real-time
    const rt = d7.children[0];
    expect(rt.level).toBe('resultType');
    expect(rt.children).toHaveLength(1); // 用例 C1
    const c1 = rt.children[0];
    expect(c1.level).toBe('case');
    expect(c1.resultIds).toEqual([1, 2]);
    // 勾选设备 = 其下全部叶（R4 容器语义）
    const sel = toggleNode(d7, new Set());
    expect(sel).toEqual(new Set([1, 2]));
  });
});

describe('buildPickResultTypeViewTree（INT-1034 §3.8.3 结果类型视图）', () => {
  it('result_type → 设备/API → 用例 → 叶（缺省 result_type 折叠「结果类型待补充」）', () => {
    const rows = [
      cand({ resultId: 1, taskId: 1, caseId: 'C1', deviceId: 7, resultType: 'real-time' }),
      cand({ resultId: 2, taskId: 2, caseId: 'C1', deviceId: 8, resultType: 'real-time' }),
      cand({ resultId: 3, taskId: 1, caseId: 'C2', deviceId: 7, resultType: null }),
    ];
    const tree = buildPickResultTypeViewTree(rows);
    expect(tree).toHaveLength(2); // real-time / 结果类型待补充
    const rt = tree.find((n) => n.name === 'real-time')!;
    expect(rt.count).toBe(2);
    expect(rt.children).toHaveLength(2); // 设备 7 / 设备 8
    const d7 = rt.children.find((n) => n.id === 7)!;
    expect(d7.level).toBe('device');
    expect(d7.children).toHaveLength(1); // 用例 C1
    expect(d7.children[0].resultIds).toEqual([1]);
    const pending = tree.find((n) => n.name === '结果类型待补充')!;
    expect(pending.count).toBe(1);
    // 三视图共享同一叶集：设备/结果类型视图叶 result_id 与用例视图一致
    expect(collectLeafResultIds(tree).sort((a, b) => a - b)).toEqual([1, 2, 3]);
  });
});

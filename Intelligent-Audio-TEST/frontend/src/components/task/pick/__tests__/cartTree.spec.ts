// -*- coding: utf-8 -*-
/**
 * 购物车树纯逻辑测试（INT-577 §4.2）——按来源任务→用例→设备/API→result_type 分组。
 */
import { describe, it, expect } from 'vitest';
import { buildCartTree, toggleCartNode, cartNodeState } from '../cartTree';
import type { PickCartGroup } from '../../../../infrastructure/api/cherryPickApi';

function group(items: Array<Record<string, unknown>>): PickCartGroup {
  return {
    sourceTaskId: 1,
    sourceTaskName: '任务A',
    items: items as any,
  };
}

describe('buildCartTree（购物车四级分组）', () => {
  it('任务→用例→设备→result_type 四级分组，叶 = item_id', () => {
    const tree = buildCartTree([
      group([
        { itemId: 1, resultId: 11, sourceCaseId: 'C1', sourceCaseName: '用例1', sourceDeviceId: 7, sourceResultType: 'real-time' },
        { itemId: 2, resultId: 12, sourceCaseId: 'C1', sourceCaseName: '用例1', sourceDeviceId: 7, sourceResultType: 'final' },
        { itemId: 3, resultId: 13, sourceCaseId: 'C2', sourceCaseName: '用例2', sourceDeviceId: 8, sourceResultType: 'default' },
      ]),
    ]);
    expect(tree).toHaveLength(1);
    const task = tree[0];
    expect(task.level).toBe('task');
    expect(task.count).toBe(3);
    expect(task.children).toHaveLength(2); // C1 / C2
    const c1 = task.children[0];
    expect(c1.name).toBe('用例1');
    expect(c1.children).toHaveLength(1); // 设备 7
    const dev = c1.children[0];
    expect(dev.kind).toBe('device');
    expect(dev.children).toHaveLength(2); // real-time / final
    expect(dev.children[0].itemIds).toEqual([1]);
    expect(dev.children[1].itemIds).toEqual([2]);
  });

  it('API 型条目落到 API 节点（kind=api）', () => {
    const tree = buildCartTree([
      group([
        { itemId: 9, resultId: 91, sourceCaseId: 'C1', sourceApiId: 101, sourceResultType: 'streaming' },
      ]),
    ]);
    const dim = tree[0].children[0].children[0];
    expect(dim.kind).toBe('api');
    expect(dim.name).toBe('API 101');
  });
});

describe('cartNodeState / toggleCartNode（节点批量移除选择联动）', () => {
  const tree = buildCartTree([
    group([
      { itemId: 1, resultId: 11, sourceCaseId: 'C1', sourceDeviceId: 7, sourceResultType: 'real-time' },
      { itemId: 2, resultId: 12, sourceCaseId: 'C1', sourceDeviceId: 7, sourceResultType: 'final' },
    ]),
  ]);
  const task = tree[0];

  it('空选 → unchecked；全选 → checked；部分 → indeterminate', () => {
    expect(cartNodeState(task, new Set())).toBe('unchecked');
    expect(cartNodeState(task, new Set([1, 2]))).toBe('checked');
    expect(cartNodeState(task, new Set([1]))).toBe('indeterminate');
  });

  it('toggle 节点 = 整组选中/取消（对应批量移除选择）', () => {
    const sel = toggleCartNode(task, new Set());
    expect(sel).toEqual(new Set([1, 2]));
    expect(toggleCartNode(task, sel)).toEqual(new Set());
  });
});

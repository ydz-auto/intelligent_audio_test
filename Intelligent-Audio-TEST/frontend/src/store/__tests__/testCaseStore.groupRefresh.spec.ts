/**
 * INT-1313 回归：创建/编辑分组后分组视图即时刷新（新分组/改名后当前页可见，无需整页刷新）。
 *
 * 原缺陷：/start-test 用例选择页创建分组后 POST /groups 200、新分组出现在 /groups 接口，
 * 但分组视图仍显示旧分组数；整页刷新后才可见。
 *
 * 根因：useTestCaseGroups.addGroup/updateGroup 只更新 fullGroupsMap/allGroups，
 * 未同步 groupsList（分组视图计数/展开按名称解析 id）也未重跑 organizeTestCasesByGroup()
 * （testCaseGroups 即分组视图渲染依赖的 store Record）。
 *
 * 锁定行为：
 * - addGroup 成功后 groupsList 立即包含新分组（testCaseCount=0），testCaseGroups 出现新分组桶；
 * - updateGroup 改名后 groupsList 条目与新名称同步，testCaseGroups 以新名称为键；
 * - fullGroupsMap 同步更新。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

import { useTestCaseStore } from '../testCaseStore';

const testcasesPortMocks = vi.hoisted(() => ({
  getGroups: vi.fn(),
  getAll: vi.fn(),
  createGroup: vi.fn(),
  updateGroup: vi.fn(),
  deleteGroup: vi.fn(),
}));

vi.mock('../../composables/testCase/testcasesPort', () => ({
  testcasesPort: testcasesPortMocks,
}));

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
});

describe('INT-1313：创建分组后分组视图即时刷新', () => {
  it('addGroup 成功后 groupsList 立即包含新分组，testCaseGroups 出现新分组桶', async () => {
    testcasesPortMocks.createGroup.mockResolvedValue({
      id: 101,
      name: '接线测试_新建分组',
      description: '新分组描述',
    });

    const store = useTestCaseStore();
    const ok = await store.addGroup({
      name: '接线测试_新建分组',
      description: '新分组描述',
    });

    expect(ok).toBe(true);
    // 新分组同步进 groupsList（分组视图计数/展开按名称解析 id）
    const groupEntry = store.groupsList.find(g => g.name === '接线测试_新建分组');
    expect(groupEntry).toBeDefined();
    expect(groupEntry!.id).toBe('101');
    expect(groupEntry!.testCaseCount).toBe(0);
    // testCaseGroups（分组视图渲染依赖的 Record）立即出现新分组桶
    expect(Object.keys(store.testCaseGroups)).toContain('接线测试_新建分组');
    expect(store.testCaseGroups['接线测试_新建分组']).toEqual([]);
    // fullGroupsMap 同步
    expect(store.fullGroupsMap['101']?.name).toBe('接线测试_新建分组');
  });

  it('addGroup 成功后分组视图分组总数即时增加（无需整页刷新）', async () => {
    testcasesPortMocks.getGroups.mockResolvedValue({
      items: [
        { id: 'g1', name: '分组A', testCaseCount: 30 },
        { id: 'g2', name: '分组B', testCaseCount: 20 },
      ],
      total: 2, page: 1, perPage: 1000, pages: 1,
    });
    testcasesPortMocks.getAll.mockResolvedValue({
      items: [],
      total: 0, page: 1, perPage: 50, pages: 1,
    });
    await useTestCaseStore().fetchTestCases();
    vi.clearAllMocks();

    testcasesPortMocks.createGroup.mockResolvedValue({ id: 103, name: '接线测试_第三组' });

    const store = useTestCaseStore();
    await store.addGroup({ name: '接线测试_第三组' });

    // 分组视图按 testCaseGroups 的键渲染 → 新分组立即可见
    expect(Object.keys(store.testCaseGroups)).toEqual(
      expect.arrayContaining(['分组A', '分组B', '接线测试_第三组'])
    );
    expect(store.groupsList.map(g => g.name)).toEqual(
      expect.arrayContaining(['分组A', '分组B', '接线测试_第三组'])
    );
  });
});

describe('INT-1313：编辑分组（改名）后分组视图即时刷新', () => {
  it('updateGroup 改名后 groupsList 条目同步新名称，testCaseGroups 以新名称为键', async () => {
    testcasesPortMocks.getGroups.mockResolvedValue({
      items: [
        { id: 'g1', name: '接线测试_原名', testCaseCount: 3 },
      ],
      total: 1, page: 1, perPage: 1000, pages: 1,
    });
    testcasesPortMocks.getAll.mockResolvedValue({
      items: [{ id: 1, name: '用例1', type: 'e2e', groupId: 'g1', groupName: '接线测试_原名' }],
      total: 1, page: 1, perPage: 50, pages: 1,
    });
    const store = useTestCaseStore();
    await store.fetchTestCases();
    vi.clearAllMocks();

    testcasesPortMocks.updateGroup.mockResolvedValue(undefined);

    await store.updateGroup('接线测试_原名', { name: '接线测试_新名', description: '改名描述' });

    // groupsList 条目改名（分组视图计数/展开按新名称解析 id）
    const renamedEntry = store.groupsList.find(g => g.name === '接线测试_新名');
    expect(renamedEntry).toBeDefined();
    expect(renamedEntry!.id).toBe('g1');
    // 旧名称不再出现在 groupsList / testCaseGroups
    expect(store.groupsList.some(g => g.name === '接线测试_原名')).toBe(false);
    expect(Object.keys(store.testCaseGroups)).not.toContain('接线测试_原名');
    // testCaseGroups 以新名称为键，用例跟随归桶
    expect(store.testCaseGroups['接线测试_新名'].map(c => c.id)).toEqual([1]);
    // fullGroupsMap 同步
    expect(store.fullGroupsMap['g1']?.name).toBe('接线测试_新名');
  });
});

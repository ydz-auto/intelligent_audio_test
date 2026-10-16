/**
 * INT-249 回归：分组视图「未分组」虚拟分组 + E2E/API 页默认标签视图。
 *
 * 缺陷：分组视图数据仅来自 fetchTestCases 的首页分页（getGroups + getAll(perPage=50)），
 * 无分组绑定的用例（用户实机 570+ 条）既无归属桶也无计数，被静默吞掉；
 * 且容器默认分组视图，用户以标签组织的数据在 E2E/API 页不可见。
 *
 * 锁定行为：
 * - fetchTestCases 挂载「未分组」虚拟分组，计数 = 用例总数 − Σ分组计数；
 * - 无分组用例 organize 进「未分组」桶；无未分组用例 / 回收站收藏口径 / 分组名冲突时不挂载；
 * - fetchCasesByGroup('__ungrouped__') 走无 groupId 大页 + 前端过滤分支；
 * - 容器默认视图为 tag（显式传 viewMode 仍可覆盖）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

import { UNGROUPED_GROUP_ID, UNGROUPED_GROUP_NAME, UNGROUPED_GROUP_FETCH_SIZE } from '../../domain';
import { ViewMode } from '../../domain/enums';
import { useTestCaseStore } from '../testCaseStore';
import { createContainerState } from '../../components/common/test-case/testCaseListContainer.state';

const testcasesPortMocks = vi.hoisted(() => ({
  getGroups: vi.fn(),
  getAll: vi.fn(),
}));

vi.mock('../../composables/testCase/testcasesPort', () => ({
  testcasesPort: testcasesPortMocks,
}));

const caseOf = (id: number | string, overrides: Record<string, unknown> = {}) => ({
  id,
  name: `用例${id}`,
  type: 'e2e',
  tags: ['HJ'],
  createdAt: '2026-01-01T00:00:00',
  updatedAt: '2026-01-01T00:00:00',
  ...overrides,
});

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
});

describe('INT-249：分组视图未分组虚拟分组', () => {
  it('fetchTestCases 挂载未分组虚拟分组：计数 = 总数 − Σ分组计数', async () => {
    testcasesPortMocks.getGroups.mockResolvedValue({
      items: [
        { id: 'g1', name: '分组A', testCaseCount: 30 },
        { id: 'g2', name: '分组B', testCaseCount: 20 },
      ],
      total: 2, page: 1, perPage: 1000, pages: 1,
    });
    // 首页 50 条里的两条：一条有分组，一条无分组
    testcasesPortMocks.getAll.mockResolvedValue({
      items: [caseOf(1, { groupId: 'g1', groupName: '分组A' }), caseOf(2)],
      total: 100, page: 1, perPage: 50, pages: 2,
    });

    const store = useTestCaseStore();
    await store.fetchTestCases({ testType: 'e2e' });

    const virtual = store.groupsList.find(g => g.id === UNGROUPED_GROUP_ID);
    expect(virtual).toBeDefined();
    expect(virtual!.name).toBe(UNGROUPED_GROUP_NAME);
    expect(virtual!.testCaseCount).toBe(50);
    // 虚拟分组同步进 fullGroupsMap：organize 预建桶 + 懒加载分支按名解析
    expect(store.fullGroupsMap[UNGROUPED_GROUP_ID]?.name).toBe(UNGROUPED_GROUP_NAME);
    // 首页无分组用例归入「未分组」桶
    expect(store.testCaseGroups[UNGROUPED_GROUP_NAME].map(c => c.id)).toEqual([2]);
  });

  it('首页无未分组用例时仍预建空桶（保证分组视图头部可见）', async () => {
    testcasesPortMocks.getGroups.mockResolvedValue({
      items: [{ id: 'g1', name: '分组A', testCaseCount: 30 }],
      total: 1, page: 1, perPage: 1000, pages: 1,
    });
    testcasesPortMocks.getAll.mockResolvedValue({
      items: [caseOf(1, { groupId: 'g1', groupName: '分组A' })],
      total: 100, page: 1, perPage: 50, pages: 2,
    });

    const store = useTestCaseStore();
    await store.fetchTestCases();

    expect(store.testCaseGroups[UNGROUPED_GROUP_NAME]).toEqual([]);
    expect(store.groupsList.find(g => g.id === UNGROUPED_GROUP_ID)?.testCaseCount).toBe(70);
  });

  it('无未分组用例（总数 = Σ分组计数）时不挂载虚拟分组', async () => {
    testcasesPortMocks.getGroups.mockResolvedValue({
      items: [
        { id: 'g1', name: '分组A', testCaseCount: 30 },
        { id: 'g2', name: '分组B', testCaseCount: 20 },
      ],
      total: 2, page: 1, perPage: 1000, pages: 1,
    });
    testcasesPortMocks.getAll.mockResolvedValue({
      items: [caseOf(1, { groupId: 'g1', groupName: '分组A' })],
      total: 50, page: 1, perPage: 50, pages: 1,
    });

    const store = useTestCaseStore();
    await store.fetchTestCases();

    expect(store.groupsList.find(g => g.id === UNGROUPED_GROUP_ID)).toBeUndefined();
    expect(store.fullGroupsMap[UNGROUPED_GROUP_ID]).toBeUndefined();
  });

  it('回收站/收藏口径跳过虚拟分组（groups 计数为活跃集合口径，与 total 不可比）', async () => {
    testcasesPortMocks.getGroups.mockResolvedValue({
      items: [{ id: 'g1', name: '分组A', testCaseCount: 30 }],
      total: 1, page: 1, perPage: 1000, pages: 1,
    });
    testcasesPortMocks.getAll.mockResolvedValue({
      items: [caseOf(9)],
      total: 18, page: 1, perPage: 50, pages: 1,
    });

    const store = useTestCaseStore();
    await store.fetchTestCases({ onlyDeleted: true, favorite: false });

    expect(store.groupsList.find(g => g.id === UNGROUPED_GROUP_ID)).toBeUndefined();
  });

  it('已存在同名真实分组时不挂载虚拟分组（避免同桶双计）', async () => {
    testcasesPortMocks.getGroups.mockResolvedValue({
      items: [
        { id: 'g1', name: UNGROUPED_GROUP_NAME, testCaseCount: 5 },
        { id: 'g2', name: '分组B', testCaseCount: 5 },
      ],
      total: 2, page: 1, perPage: 1000, pages: 1,
    });
    testcasesPortMocks.getAll.mockResolvedValue({
      items: [caseOf(1, { groupId: 'g1', groupName: UNGROUPED_GROUP_NAME })],
      total: 100, page: 1, perPage: 50, pages: 2,
    });

    const store = useTestCaseStore();
    await store.fetchTestCases();

    expect(store.groupsList.filter(g => g.name === UNGROUPED_GROUP_NAME)).toHaveLength(1);
    expect(store.groupsList.find(g => g.id === UNGROUPED_GROUP_ID)).toBeUndefined();
  });

  it('fetchCasesByGroup 未分组分支：无 groupId 过滤 + 大页拉取 + 前端过滤', async () => {
    testcasesPortMocks.getGroups.mockResolvedValue({
      items: [{ id: 'g1', name: '分组A', testCaseCount: 1 }],
      total: 1, page: 1, perPage: 1000, pages: 1,
    });
    testcasesPortMocks.getAll
      .mockResolvedValueOnce({
        items: [caseOf(1, { groupId: 'g1', groupName: '分组A' }), caseOf(2), caseOf(3)],
        total: 3, page: 1, perPage: 50, pages: 1,
      })
      .mockResolvedValueOnce({
        items: [
          caseOf(2, { groupId: 'g1', groupName: '分组A' }),
          caseOf(3),
          caseOf(4),
          // 孤儿分组用例：groupId 指向已删分组（groupName 为空）→ 与归桶规则一致，归入未分组
          caseOf(5, { groupId: 'ghost-group', groupName: undefined }),
        ],
        total: 4, page: 1, perPage: 1000, pages: 1,
      });

    const store = useTestCaseStore();
    await store.fetchTestCases();
    vi.clearAllMocks();

    await store.fetchCasesByGroup(UNGROUPED_GROUP_ID, { testType: 'e2e' });

    expect(testcasesPortMocks.getAll).toHaveBeenCalledWith(
      expect.objectContaining({
        page: 1,
        perPage: UNGROUPED_GROUP_FETCH_SIZE,
        groupId: undefined,
        type: 'e2e',
      })
    );
    // 无分组绑定 + 孤儿分组用例进入未分组桶；有效分组用例排除
    expect(store.testCaseGroups[UNGROUPED_GROUP_NAME].map(c => c.id)).toEqual([3, 4, 5]);
    expect(store.loadedGroupCases[UNGROUPED_GROUP_ID]?.map(c => c.id)).toEqual([3, 4, 5]);
    // 单页封口：不出现「加载更多」
    expect(store.groupPagination[UNGROUPED_GROUP_ID]?.pages).toBe(1);
    expect(store.hasMoreGroupCases(UNGROUPED_GROUP_ID)).toBe(false);
  });
});

describe('INT-249：容器默认视图为标签视图', () => {
  it('未传 viewMode 时默认 tag（E2E/API 测试流路径）', () => {
    const state = createContainerState({});
    expect(state.innerViewMode.value).toBe(ViewMode.TAG);
  });

  it('显式传 viewMode 时跟随（TestCaseManager 分组视图路径）', () => {
    const state = createContainerState({ viewMode: 'group' });
    expect(state.innerViewMode.value).toBe(ViewMode.GROUP);
  });
});

describe('INT-526：回收站态分组展开透传 onlyDeleted（§5.3 双视图贯通）', () => {
  it('fetchCasesByGroup 回收站态（onlyDeleted=true）入参透传', async () => {
    testcasesPortMocks.getAll.mockResolvedValue({
      items: [caseOf(1, { groupId: 'g1', groupName: '分组A', deleted: true })],
      total: 1, page: 1, perPage: 20, pages: 1,
    });

    const store = useTestCaseStore();
    await store.fetchCasesByGroup('g1', { onlyDeleted: true });

    expect(testcasesPortMocks.getAll).toHaveBeenCalledWith(expect.objectContaining({ onlyDeleted: true, groupId: 'g1' }));
    // 已删用例装载进 loadedGroupCases（卡片 meta 带 deleted）
    expect(store.loadedGroupCases['g1']?.map(c => c.id)).toEqual([1]);
    expect(store.loadedGroupCases['g1']?.[0]?.deleted).toBe(true);
  });

  it('fetchCasesByGroup 普通态默认 onlyDeleted=false（活跃口径）', async () => {
    testcasesPortMocks.getAll.mockResolvedValue({
      items: [caseOf(1, { groupId: 'g1', groupName: '分组A' })],
      total: 1, page: 1, perPage: 20, pages: 1,
    });

    const store = useTestCaseStore();
    await store.fetchCasesByGroup('g1');

    expect(testcasesPortMocks.getAll).toHaveBeenCalledWith(expect.objectContaining({ onlyDeleted: false }));
  });

  it('loadMoreGroupCases 分页续拉携带 onlyDeleted（翻页不回退活跃口径）', async () => {
    testcasesPortMocks.getAll
      .mockResolvedValueOnce({
        items: [caseOf(1, { groupId: 'g1', groupName: '分组A', deleted: true })],
        total: 3, page: 1, perPage: 20, pages: 2,
      })
      .mockResolvedValueOnce({
        items: [caseOf(2, { groupId: 'g1', groupName: '分组A', deleted: true })],
        total: 3, page: 2, perPage: 20, pages: 2,
      });

    const store = useTestCaseStore();
    await store.fetchCasesByGroup('g1', { onlyDeleted: true });
    vi.clearAllMocks();
    await store.loadMoreGroupCases('g1');

    expect(testcasesPortMocks.getAll).toHaveBeenCalledWith(expect.objectContaining({ page: 2, onlyDeleted: true }));
    expect(store.loadedGroupCases['g1']?.map(c => c.id)).toEqual([1, 2]);
  });
});

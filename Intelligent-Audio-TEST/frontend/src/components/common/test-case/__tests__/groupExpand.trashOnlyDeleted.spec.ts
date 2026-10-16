/**
 * INT-526 回归：回收站态分组展开懒加载透传 onlyDeleted。
 *
 * 缺陷：useTestCaseGroupExpand.toggleCategory 调用 store.fetchCasesByGroup 时
 * 未透传 onlyDeleted（仅 includeDeleted），回收站态分组懒加载走活跃用例口径，
 * 已删用例不可见（INT-331 实测，测试锚点
 * tests/ui/test_ui_12_int331_fav_trash_algo_modal.py::test_testcase_trash_expanded_group_missing_only_deleted）。
 *
 * 本 spec 锁定容器编排层 wiring：
 * - props.trashMode=true → toggleCategory → fetchCasesByGroup → getAll(onlyDeleted=true)
 * - 普通态展开 → onlyDeleted=false（活跃口径，与主拉取 fetchTestCases 一致）
 * - 进出回收站清空已加载分组用例缓存（普通态缓存不污染回收站态）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { reactive, nextTick } from 'vue';
import { createPinia, setActivePinia } from 'pinia';

const ports = vi.hoisted(() => ({
  getAll: vi.fn(),
}));

vi.mock('@/composables/testCase/testcasesPort', () => ({ testcasesPort: ports }));

import { createContainerState } from '../testCaseListContainer.state';
import { createGroupExpandModule } from '../testCaseListContainer.groupExpand';
import { useTestCaseStore } from '@/store/testCaseStore';

beforeEach(() => {
  vi.clearAllMocks();
  setActivePinia(createPinia());
  ports.getAll.mockResolvedValue({ items: [], total: 0, page: 1, perPage: 20, pages: 1 });
});

const setup = (trashMode: boolean) => {
  const props = reactive({ viewMode: 'group', trashMode });
  const state = createContainerState(props);
  const emit = vi.fn();
  const mod = createGroupExpandModule(props, emit, state);
  return { props, state, mod };
};

const seedGroup = () => {
  const store = useTestCaseStore();
  // Pinia setup store ref 自动解包：直接赋值（store.groupsList 已是数组）
  store.groupsList = [{ id: 'g1', name: '分组A', testCaseCount: 0 }];
  store.fullGroupsMap = { g1: { id: 'g1', name: '分组A' } as any };
  return store;
};

describe('INT-526：回收站态分组展开透传 onlyDeleted（§5.3 双视图贯通）', () => {
  it('回收站态展开分组：toggleCategory → fetchCasesByGroup 入参 onlyDeleted=true', async () => {
    const { mod } = setup(true);
    seedGroup();

    await mod.toggleCategory('分组A');

    expect(ports.getAll).toHaveBeenCalledWith(expect.objectContaining({ onlyDeleted: true, groupId: 'g1' }));
  });

  it('普通态展开分组：onlyDeleted=false（活跃口径）', async () => {
    const { mod } = setup(false);
    seedGroup();

    await mod.toggleCategory('分组A');

    expect(ports.getAll).toHaveBeenCalledWith(expect.objectContaining({ onlyDeleted: false, groupId: 'g1' }));
  });

  it('进出回收站清空已加载分组用例缓存（普通态缓存不污染回收站态展开）', async () => {
    const { props, mod } = setup(false);
    const store = seedGroup();

    await mod.toggleCategory('分组A'); // 普通态展开，装载活跃用例缓存
    expect(store.loadedGroupCases['g1']).toBeDefined();

    props.trashMode = true;
    await nextTick();
    // trashMode watch → resetGroupCache：loadedGroupCases / groupPagination 清空，
    // 回收站态展开会按 onlyDeleted=true 重新拉取（而非复用活跃缓存）
    expect(store.loadedGroupCases).toEqual({});
    expect(store.groupPagination).toEqual({});
  });
});

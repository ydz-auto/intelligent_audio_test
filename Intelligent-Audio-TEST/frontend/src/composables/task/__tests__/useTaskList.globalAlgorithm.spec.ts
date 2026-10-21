/**
 * INT-1112：全局算法联动（B03 / React INT-1033 对齐）。
 *
 * 锁定口径：
 * - 持久化全局算法（localStorage `iatp:algorithm:v1`）在真实 /algorithm/options 内 → 列表请求自动附 algorithm_type；
 * - 陈旧/无效全局值（不在真实选项内）→ 静默回落「全部算法」——不发 algorithm_type，后端即返回全部（不筛空）；
 * - 页面内算法筛选（filters.algorithmType）优先于全局（未设页面筛选才继承全局）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

const mocks = vi.hoisted(() => ({
  getAll: vi.fn(),
  getDomainStats: vi.fn(),
  getOptions: vi.fn(),
}));

vi.mock('@/composables/task/tasksPort', () => ({
  tasksPort: { getAll: mocks.getAll, getDomainStats: mocks.getDomainStats },
}));

vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: { getOptions: mocks.getOptions },
}));

import { useTaskList } from '../useTaskList';
import { useGlobalAlgorithmStore } from '../../../store/globalAlgorithmStore';

const PAGE = { items: [], total: 0, page: 1, perPage: 10, pages: 1 };
const AGG = {
  total: 0, deletedTotal: 0, statusCounts: {}, typeCounts: {}, trend: [], granularity: 'day',
};

const lastTasksQuery = () => {
  const calls = mocks.getAll.mock.calls;
  return calls[calls.length - 1]?.[0] as Record<string, any>;
};

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
  localStorage.clear();
  mocks.getAll.mockResolvedValue(PAGE);
  mocks.getDomainStats.mockResolvedValue(AGG);
});

describe('INT-1112 全局算法联动', () => {
  it('有效持久化全局算法 → 列表请求自动附 algorithm_type', async () => {
    localStorage.setItem('iatp:algorithm:v1', 'voice_llm');
    mocks.getOptions.mockResolvedValue({ algorithms: [{ value: 'voice_llm', name: '小艺语音大模型' }] });

    const vm = useTaskList();
    await vm.fetchTasks();

    const params = lastTasksQuery();
    expect(params.algorithmType).toBe('voice_llm');
  });

  it('陈旧/无效持久化全局值 → 回落「全部算法」，不发 algorithm_type（不筛空）', async () => {
    localStorage.setItem('iatp:algorithm:v1', 'no_such_algo_xyz');
    mocks.getOptions.mockResolvedValue({ algorithms: [{ value: 'voice_llm', name: '小艺语音大模型' }] });

    const vm = useTaskList();
    await vm.fetchTasks();

    const params = lastTasksQuery();
    expect(params.algorithmType).toBeUndefined();
    expect(vm.effectiveAlgorithmType.value).toBe('');
    expect(vm.globalAlgorithmValid.value).toBe(false);
  });

  it('页面内算法筛选优先于全局（未设页面筛选才继承全局）', async () => {
    localStorage.setItem('iatp:algorithm:v1', 'voice_llm');
    mocks.getOptions.mockResolvedValue({ algorithms: [{ value: 'voice_llm', name: '小艺语音大模型' }] });

    const vm = useTaskList();
    vm.filters.value.algorithmType = 'asr';
    await vm.fetchTasks();

    const params = lastTasksQuery();
    expect(params.algorithmType).toBe('asr');
  });

  it('全局算法切换（store.selectedType 变化）→ effectiveAlgorithmType 更新', async () => {
    mocks.getOptions.mockResolvedValue({ algorithms: [{ value: 'voice_llm', name: '小艺语音大模型' }] });

    const vm = useTaskList();
    expect(vm.effectiveAlgorithmType.value).toBe('');
    // 等 loadAlgorithms（/algorithm/options）异步落定，算法列表灌入 store
    await new Promise(resolve => setTimeout(resolve, 0));
    // 模拟右上角切换器选中全局算法（与 useTaskList 共用同一 Pinia store 实例）
    const store = useGlobalAlgorithmStore();
    store.setAlgorithm('voice_llm');

    expect(vm.globalAlgorithmValid.value).toBe(true);
    expect(vm.effectiveAlgorithmType.value).toBe('voice_llm');
  });
});

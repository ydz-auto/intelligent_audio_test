/**
 * INT-290：HistoryReports 加载指示缺失回归。
 *
 * 缺陷（INT-261 C 域 UX 审计）：loading ref 贯穿 loadReports 但模板无任何加载指示。
 * 锁定契约：
 * 1. 请求挂起期间渲染 .history-reports-loading-bar（对齐 A/B 域 loading bar 方案），
 *    且不显示「暂无报告数据」空态；
 * 2. 加载完成后 loading bar 消失、报告列表正常渲染。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { nextTick } from 'vue';
import { createPinia, setActivePinia } from 'pinia';

const mocks = vi.hoisted(() => ({
  getAll: vi.fn(),
  getTabCounts: vi.fn(),
  openModal: vi.fn(),
  restore: vi.fn(),
  purge: vi.fn(),
  toggleFavorite: vi.fn(),
  favoriteOnly: vi.fn(),
}));

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/composables/report/reportsPort', () => ({
  reportsPort: {
    getAll: mocks.getAll,
    getTabCounts: mocks.getTabCounts,
    secondaryCompare: vi.fn(),
    batchDelete: vi.fn(),
    delete: vi.fn(),
    publish: vi.fn(),
  },
}));

vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({ open: mocks.openModal }),
}));

vi.mock('@/composables/modal/constants', () => ({
  MODAL_TYPES: {
    BASIC_CONFIRM: 'basicConfirm',
    DELETE_CONFIRM: 'deleteConfirm',
  },
}));

vi.mock('@/composables/algorithm/useAlgorithmLabels', () => ({
  useAlgorithmLabels: () => ({
    algorithmOptions: { value: [] },
    loadAlgorithms: vi.fn(),
    getAlgorithmLabel: vi.fn(),
  }),
}));

vi.mock('@/utils/socket', () => ({
  default: { connect: vi.fn(), on: vi.fn(), off: vi.fn() },
}));

vi.mock('@/composables/favorite/useFavorites', () => ({
  useFavorites: () => ({
    favoriteOnly: { value: false },
    favoriteIds: { value: new Set<string>() },
    isFavorite: vi.fn(() => false),
    toggleFavorite: vi.fn(),
    loadFavorites: vi.fn(),
    restore: mocks.restore,
    purge: mocks.purge,
  }),
}));

// 子组件浅替身：页面级契约测试不渲染其内部
vi.mock('../../components/common/BadgeFilter.vue', () => ({
  default: { template: '<div class="badge-filter-stub" />', props: ['options', 'modelValue', 'allLabel', 'title'] },
}));
vi.mock('../../components/common/FavoriteTrashBar.vue', () => ({
  default: { template: '<div class="favorite-trash-bar-stub" />', props: ['favoriteOnly', 'trashMode', 'favoriteDisabled'] },
}));
vi.mock('../../components/algorithm/AlgorithmFilter.vue', () => ({
  default: { template: '<div class="algorithm-filter-stub" />', props: ['options', 'modelValue', 'title'] },
}));
vi.mock('../../components/common/data/PaginationComponent.vue', () => ({
  default: { template: '<div class="pagination-stub" />', props: ['currentPage', 'pageSize', 'totalItems'] },
}));

import HistoryReports from '../HistoryReports.vue';
import { useAuthStore } from '../../../store/authStore';

const EMPTY_PAGE = { items: [], total: 0, page: 1, per_page: 10, pages: 1 };
const ONE_PAGE = {
  items: [
    { id: 'r1', name: '报告A', status: 'published', type: 'task', createdAt: '2026-10-01', summary: { totalCases: 3, completedCases: 2, failedCases: 1, overallSuccessRate: 66.7 } },
  ],
  total: 1, page: 1, per_page: 10, pages: 1,
};

/** 可手动 resolve 的延迟 Promise（模拟请求挂起） */
function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((res) => { resolve = res; });
  return { promise, resolve };
}

beforeEach(() => {
  vi.clearAllMocks();
  // INT-483：组件 setup 新增 useAuthStore 权限显隐（benchmark:report:publish 发布入口），测试注入 Pinia 并置 admin 权限
  setActivePinia(createPinia());
  useAuthStore().setAuth('t', { id: 1, username: 'u', roleId: null, roleName: '', permissions: ['*'] });
  mocks.getAll.mockResolvedValue(EMPTY_PAGE);
  mocks.getTabCounts.mockResolvedValue({ all: 1, draft: 0, published: 1, comparison: 0 });
});

describe('加载指示（INT-290）', () => {
  it('请求挂起期间渲染 loading bar，且不显示空数据提示', async () => {
    const d = deferred<any>();
    mocks.getAll.mockReturnValue(d.promise);

    const wrapper = mount(HistoryReports);
    await nextTick();

    expect(wrapper.find('.history-reports-loading-bar').exists()).toBe(true);
    expect(wrapper.find('.history-reports-loading-bar').text()).toContain('正在加载报告');
    // 加载中不闪「暂无报告数据」空态
    expect(wrapper.find('.no-data').exists()).toBe(false);

    d.resolve(ONE_PAGE);
    await flushPromises();

    expect(wrapper.find('.history-reports-loading-bar').exists()).toBe(false);
  });

  it('加载完成后 loading bar 消失、报告列表正常渲染', async () => {
    mocks.getAll.mockResolvedValue(ONE_PAGE);

    const wrapper = mount(HistoryReports);
    await flushPromises();

    expect(wrapper.find('.history-reports-loading-bar').exists()).toBe(false);
    expect(wrapper.text()).toContain('报告A');
  });
});

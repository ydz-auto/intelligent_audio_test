/**
 * INT-536（D1）：HistoryReports 报告列表编辑/删除入口 canEditResource 门控回归。
 *
 * 契约：私有报告非 owner（含 admin 豁免）隐藏「编辑」与「删除」入口；
 *      共享报告回落既有权限点保留入口；owner 私有报告保留入口。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { useAuthStore } from '@/store/authStore';

const mocks = vi.hoisted(() => ({
  openModal: vi.fn(),
  getAll: vi.fn(),
  toggleFavorite: vi.fn(),
  favoriteOnly: vi.fn(),
  restore: vi.fn(),
  purge: vi.fn(),
}));

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ query: {} }),
}));

vi.mock('@/composables/report/reportsPort', () => ({
  reportsPort: {
    getAll: mocks.getAll,
    secondaryCompare: vi.fn(),
    batchDelete: vi.fn(),
    delete: vi.fn(),
    publish: vi.fn(),
  },
}));

vi.mock('@/composables/report/reportChannelPort', () => ({
  reportChannelPort: {
    connect: vi.fn(),
    onReportGenerated: vi.fn(),
    offReportGenerated: vi.fn(),
    onSecondaryCompareGenerated: vi.fn(),
    offSecondaryCompareGenerated: vi.fn(),
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
    favoriteOnly: mocks.favoriteOnly(),
    favoriteIds: { value: new Set<string>() },
    isFavorite: vi.fn(() => false),
    toggleFavorite: mocks.toggleFavorite,
    loadFavorites: vi.fn(),
    restore: mocks.restore,
    purge: mocks.purge,
  }),
}));

// 子组件替身：本用例只测报告卡片行操作门控
vi.mock('../../components/common/BadgeFilter.vue', () => ({
  default: { template: '<div class="badge-filter-stub" />', props: ['options', 'modelValue', 'allLabel', 'title'] },
}));
vi.mock('../../components/common/FavoriteTrashBar.vue', () => ({
  default: { template: '<div class="favorite-trash-stub" />', props: ['favoriteOnly', 'trashMode'] },
}));
vi.mock('../../components/common/data/PaginationComponent.vue', () => ({
  default: { template: '<div class="pagination-stub" />' },
}));
vi.mock('../../components/common/visibility/VisibilityBadge.vue', () => ({
  default: { template: '<span class="visibility-badge-stub" />', props: ['visibility'] },
}));
vi.mock('../../components/algorithm/AlgorithmFilter.vue', () => ({
  default: { template: '<div class="algorithm-filter-stub" />', props: ['options', 'modelValue', 'title'] },
}));

import HistoryReports from '../HistoryReports.vue';

const REPORTS_PAGE = {
  items: [
    { id: 1, name: '共享报告', type: 'task', status: 'published', visibility: 'shared', createdByUserId: 999, createdAt: '2026-10-13T10:00:00Z', summary: { totalCases: 1 } },
    { id: 2, name: '他人私有', type: 'task', status: 'published', visibility: 'private', createdByUserId: 999, createdAt: '2026-10-13T10:00:00Z', summary: { totalCases: 1 } },
    { id: 3, name: '我的私有', type: 'task', status: 'published', visibility: 'private', createdByUserId: 1, createdAt: '2026-10-13T10:00:00Z', summary: { totalCases: 1 } },
  ],
  total: 3, page: 1, per_page: 20, pages: 1,
};

function authAs(userId: number, permissions: string[] = []) {
  setActivePinia(createPinia());
  useAuthStore().setAuth('t', { id: userId, username: 'tester', roleId: null, roleName: '', permissions });
}

async function mountPage() {
  const wrapper = mount(HistoryReports, { global: { stubs: { teleport: true } } });
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getAll.mockResolvedValue(REPORTS_PAGE);
  mocks.favoriteOnly.mockReturnValue({ value: false });
  mocks.openModal.mockResolvedValue(true);
});

describe('INT-536 D1：报告列表编辑/删除入口门控', () => {
  it('非 owner 私有报告：隐藏「编辑」与「删除」按钮', async () => {
    authAs(1);
    const wrapper = await mountPage();
    const card = wrapper.findAll('.card').find((c: any) => c.text().includes('他人私有'));
    expect(card, '他人私有报告卡片应渲染').toBeTruthy();
    expect(card!.text()).not.toContain('编辑');
    expect(card!.text()).not.toContain('删除');
  });

  it('owner 私有报告：保留「编辑」与「删除」按钮', async () => {
    authAs(1);
    const wrapper = await mountPage();
    const card = wrapper.findAll('.card').find((c: any) => c.text().includes('我的私有'));
    expect(card!.text()).toContain('编辑');
    expect(card!.text()).toContain('删除');
  });

  it('共享报告：保留「编辑」与「删除」按钮（回落既有权限点）', async () => {
    authAs(1);
    const wrapper = await mountPage();
    const card = wrapper.findAll('.card').find((c: any) => c.text().includes('共享报告'));
    expect(card!.text()).toContain('编辑');
    expect(card!.text()).toContain('删除');
  });

  it('admin 豁免：非 owner 私有报告仍保留「编辑」与「删除」按钮', async () => {
    authAs(1, ['*']);
    const wrapper = await mountPage();
    const card = wrapper.findAll('.card').find((c: any) => c.text().includes('他人私有'));
    expect(card!.text()).toContain('编辑');
    expect(card!.text()).toContain('删除');
  });
});

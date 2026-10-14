/**
 * INT-280：HistoryReports Tab 过滤服务端化回归。
 *
 * 缺陷：Tab 切换（草稿/已发布/对比）从基线的服务端过滤退化为纯客户端过滤，
 * 分页 total 是全量总数、Tab 计数只统计当前页，多页数据下「页码多页但当前
 * Tab 列表为空」。锁定：
 * 1. loadReports 按 TAB_TO_FILTER 下发服务端过滤（draft/published → status，
 *    comparison → 逗号分隔多类型；与筛选栏条件并存）
 * 2. handleTabChange：切 Tab 重置分页并重取（不再仅本地过滤）
 * 3. Tab 计数服务端聚合：getTabCount 读 tabCounts（getTabCounts 独立接口），
 *    变更动作（删除/发布/恢复/彻底删除）后计数随之刷新
 * 4. reportsApi.getTabCounts 请求 /reports/tab-counts（Infrastructure 契约）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';

const mocks = vi.hoisted(() => ({
  openModal: vi.fn(),
  getAll: vi.fn(),
  getTabCounts: vi.fn(),
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
    favoriteOnly: mocks.favoriteOnly(),
    favoriteIds: { value: new Set<string>() },
    isFavorite: vi.fn(() => isFav.value),
    toggleFavorite: mocks.toggleFavorite,
    loadFavorites: vi.fn(),
    restore: mocks.restore,
    purge: mocks.purge,
  }),
}));

import { useHistoryReports, REPORT_TABS } from '../historyReports';

/** 收藏筛选 ref（useFavorites mock 中引用同一实例） */
const favoriteOnlyRef = ref(false);
mocks.favoriteOnly.mockImplementation(() => favoriteOnlyRef);
/** 星标态 */
const isFav = ref(false);

/** Tab 计数默认桩（all=20, draft=5, published=12, comparison=3） */
const TAB_COUNTS = { all: 20, draft: 5, published: 12, comparison: 3 };
const EMPTY_PAGE = { items: [], total: 0, page: 1, per_page: 20, pages: 1 };

const lastQuery = () => {
  const calls = mocks.getAll.mock.calls;
  return calls[calls.length - 1]?.[0] as Record<string, any>;
};

beforeEach(() => {
  vi.clearAllMocks();
  favoriteOnlyRef.value = false;
  mocks.getAll.mockResolvedValue(EMPTY_PAGE);
  mocks.getTabCounts.mockResolvedValue(TAB_COUNTS);
});

describe('loadReports：Tab → 服务端过滤参数下发（INT-280 主缺陷回归）', () => {
  it('全部 Tab：不带 Tab 附加过滤', async () => {
    const ctx = useHistoryReports();
    await ctx.loadReports();
    const params = lastQuery();
    expect(params.status).toBeUndefined();
    expect(params.type).toBeUndefined();
  });

  it('草稿 Tab：下发 status=draft', async () => {
    const ctx = useHistoryReports();
    ctx.activeTab.value = REPORT_TABS.DRAFT;
    await ctx.loadReports();
    expect(lastQuery().status).toBe('draft');
    expect(lastQuery().type).toBeUndefined();
  });

  it('已发布 Tab：下发 status=published', async () => {
    const ctx = useHistoryReports();
    ctx.activeTab.value = REPORT_TABS.PUBLISHED;
    await ctx.loadReports();
    expect(lastQuery().status).toBe('published');
  });

  it('对比 Tab：下发逗号分隔多类型（comparison,secondary_comparison）', async () => {
    const ctx = useHistoryReports();
    ctx.activeTab.value = REPORT_TABS.COMPARISON;
    await ctx.loadReports();
    expect(lastQuery().type).toBe('comparison,secondary_comparison');
    expect(lastQuery().status).toBeUndefined();
  });

  it('Tab 过滤与筛选栏条件并存：已发布 Tab + 筛选类型 comparison 时两者同发', async () => {
    const ctx = useHistoryReports();
    ctx.activeTab.value = REPORT_TABS.PUBLISHED;
    ctx.filters.value.reportType = 'comparison';
    await ctx.loadReports();
    const params = lastQuery();
    expect(params.status).toBe('published');
    expect(params.type).toBe('comparison');
  });

  it('对比 Tab 的多类型优先于筛选栏类型（对比视图归属按类型集合）', async () => {
    const ctx = useHistoryReports();
    ctx.activeTab.value = REPORT_TABS.COMPARISON;
    ctx.filters.value.reportType = 'task';
    await ctx.loadReports();
    expect(lastQuery().type).toBe('comparison,secondary_comparison');
  });
});

describe('handleTabChange：切 Tab 重置分页并按服务端过滤重取', () => {
  it('切到草稿 Tab：页码重置 1、activeTab 更新、status=draft 重取', async () => {
    const ctx = useHistoryReports();
    ctx.selectedReports.value = new Set(['r1']);
    ctx.currentPage.value = 4;

    await ctx.handleTabChange(REPORT_TABS.DRAFT);

    expect(ctx.activeTab.value).toBe(REPORT_TABS.DRAFT);
    expect(ctx.currentPage.value).toBe(1);
    expect(ctx.selectedReports.value.size).toBe(0);
    expect(lastQuery().status).toBe('draft');
  });

  it('切回全部 Tab：过滤清空重取', async () => {
    const ctx = useHistoryReports();
    await ctx.handleTabChange(REPORT_TABS.DRAFT);
    await ctx.handleTabChange(REPORT_TABS.ALL);
    expect(lastQuery().status).toBeUndefined();
  });
});

describe('Tab 计数服务端聚合（getTabCount 不再按当前页统计）', () => {
  it('getTabCount 返回 tabCounts 服务端计数（非 allReports 长度）', async () => {
    const ctx = useHistoryReports();
    await ctx.loadTabCounts();

    expect(ctx.getTabCount('all')).toBe(20);
    expect(ctx.getTabCount('draft')).toBe(5);
    expect(ctx.getTabCount('published')).toBe(12);
    expect(ctx.getTabCount('comparison')).toBe(3);
    // 当前页 items 为空也不影响计数（多页数据不失真）
    expect(ctx.allReports.value).toHaveLength(0);
  });

  it('getTabCounts 接口失败：计数归零但不抛错（主列表不受影响）', async () => {
    const ctx = useHistoryReports();
    mocks.getTabCounts.mockRejectedValue(new Error('net down'));

    await expect(ctx.loadTabCounts()).resolves.toBeUndefined();
    expect(ctx.getTabCount('all')).toBe(0);
  });

  it('单项删除成功后刷新 Tab 计数（确认模态 onConfirm 触发）', async () => {
    const ctx = useHistoryReports();
    await ctx.loadTabCounts();
    mocks.openModal.mockImplementation(async (_type: string, options: any) => {
      await options.onConfirm();
      return true;
    });

    await ctx.deleteReport('r1');

    expect(mocks.getAll).toHaveBeenCalled();
    expect(mocks.getTabCounts).toHaveBeenCalledTimes(2); // 初始 + 变更后
  });

  it('发布成功后刷新 Tab 计数', async () => {
    const ctx = useHistoryReports();
    await ctx.loadTabCounts();
    mocks.openModal.mockImplementation(async (_type: string, options: any) => {
      await options.onConfirm();
      return true;
    });

    await ctx.publishReport('r1');

    expect(mocks.getTabCounts).toHaveBeenCalledTimes(2);
  });

  it('批量恢复成功后刷新 Tab 计数', async () => {
    const ctx = useHistoryReports();
    ctx.selectedReports.value = new Set(['r1', 'r2']);
    mocks.restore.mockResolvedValue({ restored_count: 2 });

    await ctx.handleBatchRestore();

    expect(mocks.restore).toHaveBeenCalledWith(['r1', 'r2']);
    expect(mocks.getAll).toHaveBeenCalled();
    expect(mocks.getTabCounts).toHaveBeenCalled();
  });
});

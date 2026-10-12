/**
 * INT-216：报告页收藏 / 回收站列表参数接线与切换口径（historyReports.ts）。
 *
 * 补 INT-215 未覆盖的单项动作与参数面（批量栏已有 trashBatchOps.spec）：
 * - loadReports 参数映射：favorite = favoriteOnly && !trashMode，trashMode → deleted=true
 * - toggleTrashMode：互斥清空收藏筛选 + 分页重置 + deleted 下发
 * - handleReportFavoriteFilterChange：favorite=true 下发 + 分页重置
 * - 单项 restore/purge：count 判真反馈 + BASIC_CONFIRM（补批量之外的口径）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';

const mocks = vi.hoisted(() => ({
  openModal: vi.fn(),
  getAll: vi.fn(),
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

import { useHistoryReports } from '../historyReports';

/** 收藏筛选 ref（useFavorites mock 中引用同一实例） */
const favoriteOnlyRef = ref(false);
mocks.favoriteOnly.mockImplementation(() => favoriteOnlyRef);
/** 星标态（handleToggleFavorite 反馈口径断言用） */
const isFav = ref(false);

const EMPTY_PAGE = { items: [], total: 0, page: 1, per_page: 20, pages: 1 };

const lastQuery = () => {
  const calls = mocks.getAll.mock.calls;
  return calls[calls.length - 1]?.[0] as Record<string, any>;
};

beforeEach(() => {
  vi.clearAllMocks();
  favoriteOnlyRef.value = false;
  mocks.getAll.mockResolvedValue(EMPTY_PAGE);
});

describe('loadReports：收藏 / 回收站参数映射（INT-141 口径）', () => {
  it('普通列表：不带 favorite/deleted', async () => {
    await useHistoryReports().loadReports();
    const params = lastQuery();
    expect(params.favorite).toBeUndefined();
    expect(params.deleted).toBeUndefined();
  });

  it('仅看收藏（非回收站态）：favorite=true', async () => {
    const ctx = useHistoryReports();
    favoriteOnlyRef.value = true;
    await ctx.loadReports();
    const params = lastQuery();
    expect(params.favorite).toBe(true);
    expect(params.deleted).toBeUndefined();
  });

  it('回收站态：deleted=true 且 favorite 不并发（互斥口径）', async () => {
    const ctx = useHistoryReports();
    ctx.trashMode.value = true;
    favoriteOnlyRef.value = true;
    await ctx.loadReports();
    const params = lastQuery();
    expect(params.deleted).toBe(true);
    expect(params.favorite).toBeUndefined();
  });
});

describe('toggleTrashMode / handleReportFavoriteFilterChange：切换口径', () => {
  it('进入回收站：清空收藏筛选、页码重置、deleted=true 重取', async () => {
    const ctx = useHistoryReports();
    favoriteOnlyRef.value = true;
    ctx.currentPage.value = 4;

    await ctx.toggleTrashMode();

    expect(ctx.trashMode.value).toBe(true);
    expect(favoriteOnlyRef.value).toBe(false);
    expect(ctx.currentPage.value).toBe(1);
    expect(lastQuery().deleted).toBe(true);
  });

  it('收藏筛选开启：页码重置并按 favorite=true 重取', async () => {
    const ctx = useHistoryReports();
    ctx.currentPage.value = 3;

    await ctx.handleReportFavoriteFilterChange(true);

    expect(ctx.currentPage.value).toBe(1);
    expect(lastQuery().favorite).toBe(true);
  });
});

describe('单项恢复 / 彻底删除（批量之外的单项口径）', () => {
  it('星标切换：成功后按 isFavorite 反馈；失败 error 反馈', async () => {
    const ctx = useHistoryReports();
    mocks.toggleFavorite.mockImplementation(async () => { isFav.value = true; });
    await ctx.handleToggleFavorite({ id: 'r1', name: 'rep1' } as any);
    expect(ctx.toast.value?.type).toBe('success');
    expect(ctx.toast.value?.message).toBe('已收藏');

    mocks.toggleFavorite.mockRejectedValue(new Error('net down'));
    await ctx.handleToggleFavorite({ id: 'r1', name: 'rep1' } as any);
    expect(ctx.toast.value?.type).toBe('error');
    expect(ctx.toast.value?.message).toContain('收藏操作失败');
  });

  it('restore：restored_count>0 成功反馈并刷新；count=0 提示无可恢复项', async () => {
    const ctx = useHistoryReports();
    mocks.restore.mockResolvedValue({ restored_count: 1 });
    await ctx.handleRestoreReport({ id: 'r1', name: 'rep1' } as any);
    expect(ctx.toast.value?.type).toBe('success');
    expect(ctx.toast.value?.message).toContain('已恢复');

    mocks.restore.mockResolvedValue({ restored_count: 0 });
    await ctx.handleRestoreReport({ id: 'r1', name: 'rep1' } as any);
    expect(ctx.toast.value?.type).toBe('info');
    expect(ctx.toast.value?.message).toContain('无可恢复项');
  });

  it('purge：BASIC_CONFIRM（danger + 不可恢复警示）确认后按 purged_count 判真', async () => {
    const ctx = useHistoryReports();
    mocks.openModal.mockResolvedValue(true);
    mocks.purge.mockResolvedValue({ purged_count: 1 });

    await ctx.handlePurgeReport({ id: 'r1', name: 'rep1' } as any);

    expect(mocks.openModal).toHaveBeenCalledWith('basicConfirm', expect.objectContaining({
      title: '彻底删除报告', danger: true,
    }));
    expect(ctx.toast.value?.type).toBe('success');
    expect(ctx.toast.value?.message).toContain('已彻底删除');
  });

  it('purge：count=0 提示无可删除项（权限不足可见）', async () => {
    const ctx = useHistoryReports();
    mocks.openModal.mockResolvedValue(true);
    mocks.purge.mockResolvedValue({ purged_count: 0 });

    await ctx.handlePurgeReport({ id: 'r1', name: 'rep1' } as any);

    expect(ctx.toast.value?.type).toBe('info');
    expect(ctx.toast.value?.message).toContain('无可删除项');
  });

  it('purge：用户取消确认不发起请求', async () => {
    const ctx = useHistoryReports();
    mocks.openModal.mockResolvedValue(false);

    await ctx.handlePurgeReport({ id: 'r1', name: 'rep1' } as any);

    expect(mocks.purge).not.toHaveBeenCalled();
  });
});

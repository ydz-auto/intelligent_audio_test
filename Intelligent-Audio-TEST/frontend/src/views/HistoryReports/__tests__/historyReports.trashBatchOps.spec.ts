/**
 * INT-215/S4 回归：报告回收站态批量恢复 / 批量彻底删除 + 数据集切换清空选中集。
 *
 * 缺陷：报告回收站态批量栏未适配——批量对比/批量删除对已删报告可点（no-op），
 * 且缺批量恢复/批量彻底删除（任务侧已有）。锁定：
 * 1. 批量恢复/彻底删除走 useFavorites 的 restore/purge（restored_count/purged_count 判定真实结果）
 * 2. 彻底删除必须经 BASIC_CONFIRM 模态（不可恢复 + 权限警示）
 * 3. toggleTrashMode 切换数据集时清空选中集（防普通态勾选的活跃报告流入批量彻底删除）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const mocks = vi.hoisted(() => ({
  openModal: vi.fn(),
  getAll: vi.fn(),
  restore: vi.fn(),
  purge: vi.fn(),
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
    favoriteOnly: { value: false },
    favoriteIds: { value: new Set<string>() },
    isFavorite: vi.fn(() => false),
    toggleFavorite: vi.fn(),
    loadFavorites: vi.fn(),
    restore: mocks.restore,
    purge: mocks.purge,
  }),
}));

import { useHistoryReports } from '../historyReports';

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getAll.mockResolvedValue({ items: [], total: 0 });
});

describe('INT-215/S4：报告回收站批量恢复', () => {
  it('全量选中 id 调 restore，成功后清空选中并刷新列表', async () => {
    const ctx = useHistoryReports();
    ctx.selectedReports.value = new Set(['r1', 'r2', 3]);
    mocks.restore.mockResolvedValue({ restored_count: 3 });

    await ctx.handleBatchRestore();

    expect(mocks.restore).toHaveBeenCalledTimes(1);
    expect(mocks.restore).toHaveBeenCalledWith(['r1', 'r2', 3]);
    expect(ctx.selectedReports.value.size).toBe(0);
    expect(mocks.getAll).toHaveBeenCalled();
    expect(ctx.toast.value?.type).toBe('success');
  });

  it('restored_count=0 提示无可恢复项而非假成功', async () => {
    const ctx = useHistoryReports();
    ctx.selectedReports.value = new Set(['r1']);
    mocks.restore.mockResolvedValue({ restored_count: 0 });

    await ctx.handleBatchRestore();

    expect(ctx.toast.value?.type).toBe('info');
    expect(ctx.toast.value?.message).toContain('无可恢复项');
  });

  it('restore 失败提示错误且不清空选中', async () => {
    const ctx = useHistoryReports();
    ctx.selectedReports.value = new Set(['r1']);
    mocks.restore.mockRejectedValue(new Error('network down'));

    await ctx.handleBatchRestore();

    expect(ctx.toast.value?.type).toBe('error');
    expect(ctx.selectedReports.value.size).toBe(1);
  });

  it('无选中不发起 restore', async () => {
    const ctx = useHistoryReports();
    await ctx.handleBatchRestore();
    expect(mocks.restore).not.toHaveBeenCalled();
  });
});

describe('INT-215/S4：报告回收站批量彻底删除', () => {
  it('BASIC_CONFIRM 确认后全量 id 调 purge（danger 警示），成功后清空选中并刷新', async () => {
    const ctx = useHistoryReports();
    ctx.selectedReports.value = new Set(['r1', 'r2']);
    mocks.purge.mockResolvedValue({ purged_count: 2 });
    mocks.openModal.mockImplementation(async (_type: string, options: any) => {
      await options.onConfirm();
      return true;
    });

    await ctx.handleBatchPurge();

    expect(mocks.openModal).toHaveBeenCalledWith(
      'basicConfirm',
      expect.objectContaining({ danger: true, title: '批量彻底删除报告' }),
    );
    expect(mocks.purge).toHaveBeenCalledTimes(1);
    expect(mocks.purge).toHaveBeenCalledWith(['r1', 'r2']);
    expect(ctx.selectedReports.value.size).toBe(0);
    expect(mocks.getAll).toHaveBeenCalled();
    expect(ctx.toast.value?.type).toBe('success');
  });

  it('用户取消（onConfirm 未执行）不调 purge', async () => {
    const ctx = useHistoryReports();
    ctx.selectedReports.value = new Set(['r1']);
    mocks.openModal.mockResolvedValue(false);

    await ctx.handleBatchPurge();

    expect(mocks.purge).not.toHaveBeenCalled();
  });

  it('purged_count=0 提示无可删除项（权限不足可见）', async () => {
    const ctx = useHistoryReports();
    ctx.selectedReports.value = new Set(['r1']);
    mocks.purge.mockResolvedValue({ purged_count: 0 });
    mocks.openModal.mockImplementation(async (_type: string, options: any) => {
      await options.onConfirm();
      return true;
    });

    await ctx.handleBatchPurge();

    expect(ctx.toast.value?.type).toBe('info');
    expect(ctx.toast.value?.message).toContain('无可删除项');
  });

  it('无选中不弹确认模态', async () => {
    const ctx = useHistoryReports();
    await ctx.handleBatchPurge();
    expect(mocks.openModal).not.toHaveBeenCalled();
    expect(mocks.purge).not.toHaveBeenCalled();
  });
});

describe('INT-215/S4：toggleTrashMode 数据集切换清空选中集', () => {
  it('进入回收站态清空选中集并重置页码（防活跃项流入批量彻底删除）', async () => {
    const ctx = useHistoryReports();
    ctx.selectedReports.value = new Set(['active-1', 'active-2']);
    ctx.currentPage.value = 3;

    await ctx.toggleTrashMode();

    expect(ctx.trashMode.value).toBe(true);
    expect(ctx.selectedReports.value.size).toBe(0);
    expect(ctx.currentPage.value).toBe(1);
  });
});

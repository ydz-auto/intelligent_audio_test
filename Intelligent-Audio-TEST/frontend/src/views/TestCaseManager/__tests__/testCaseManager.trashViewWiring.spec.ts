/**
 * INT-216：用例管理页收藏 / 回收站协调层单测（TestCaseManager.ts，INT-215 修复后口径）。
 *
 * 真实 pinia store + 端口 mock，锁定：
 * - currentFetchExtra 口径：favorite = favoriteOnly && !trashMode，onlyDeleted = trashMode
 * - 分组 / 标签双视图均贯通（P1 回归：标签视图漏传导致回收站断链）
 * - toggleTrashMode 互斥联动（回收站态清空收藏筛选）与刷新
 * - handleFavoriteToggle 星标切换 + patchTestCaseFavorite 就地回写
 * - restore/purge 按 restored_count/purged_count 判真（count=0 非假成功）
 * - purge/全部恢复走 BASIC_CONFIRM 模态；全部恢复按 onlyDeleted 后端圈定集合
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { nextTick } from 'vue';
import { createPinia, setActivePinia } from 'pinia';

const ports = vi.hoisted(() => ({
  getAll: vi.fn(),
  getGroups: vi.fn(),
  getTagView: vi.fn(),
  getIdsByFilter: vi.fn(),
}));
const favoritesApi = vi.hoisted(() => ({
  listFavoriteIds: vi.fn(),
  favorite: vi.fn(),
  unfavorite: vi.fn(),
  restore: vi.fn(),
  purge: vi.fn(),
}));
const modal = vi.hoisted(() => ({ open: vi.fn() }));

vi.mock('@/composables/testCase/testcasesPort', () => ({ testcasesPort: ports }));
vi.mock('@/composables/testCase/groupsPort', () => ({ groupsPort: { getAll: vi.fn() } }));
vi.mock('@/composables/shared/tagsPort', () => ({ tagsPort: { getAll: vi.fn() } }));
vi.mock('@/infrastructure/api/favoritesApi', () => favoritesApi);

vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({ open: modal.open }),
  MODAL_TYPES: { BASIC_CONFIRM: 'basicConfirm', DELETE_CONFIRM: 'deleteConfirm' },
}));

vi.mock('@/composables/testCase/useTestCaseCard', () => ({
  useTestCaseCard: () => ({
    formData: { value: {} },
    groupFormData: { value: {} },
    editingTestCase: { value: null },
    editingGroup: { value: null },
    openAddTestCaseModal: vi.fn(),
    openEditTestCaseModal: vi.fn(),
    openCreateGroupModal: vi.fn(),
    openEditGroupModal: vi.fn(),
    openImportTestCaseModal: vi.fn(),
    openExportTestCaseModal: vi.fn(),
    handleModalSave: vi.fn(),
    handleTestCaseAction: vi.fn(),
  }),
}));

vi.mock('@/composables/modal/useDeleteConfirm', () => ({
  useDeleteConfirm: () => ({ confirmDeleteGroup: vi.fn(), confirmDeleteTestCase: vi.fn() }),
}));

import { provideNotification } from '@/composables/modal/useNotification';
import { ViewMode } from '@/domain/enums';
import { useTestCaseManager } from '../TestCaseManager';

const show = vi.fn();
const EMPTY_PAGE = { items: [], total: 0, page: 1, per_page: 50, pages: 1 };

/** 最近一次列表 / 标签视图查询参数 */
const lastGetAllParams = () => {
  const calls = ports.getAll.mock.calls;
  return calls[calls.length - 1]?.[0] as Record<string, any>;
};
const lastTagViewParams = () => {
  const calls = ports.getTagView.mock.calls;
  return calls[calls.length - 1]?.[0] as Record<string, any>;
};

beforeEach(() => {
  vi.clearAllMocks();
  setActivePinia(createPinia());
  provideNotification({ show });
  ports.getAll.mockResolvedValue(EMPTY_PAGE);
  ports.getGroups.mockResolvedValue({ items: [], total: 0, page: 1, per_page: 1000, pages: 1 });
  ports.getTagView.mockResolvedValue(EMPTY_PAGE);
  ports.getIdsByFilter.mockResolvedValue({ ids: [] });
  favoritesApi.listFavoriteIds.mockResolvedValue({ task: [], report: [], testcase: [] });
  favoritesApi.restore.mockResolvedValue({ restored_count: 1 });
  favoritesApi.purge.mockResolvedValue({ purged_count: 1 });
  favoritesApi.favorite.mockResolvedValue({ entity_id: 'c1' });
});

describe('currentFetchExtra：分组 / 标签双视图参数贯通（INT-215 P1 回归）', () => {
  it('分组视图：favoriteOnly=true → favorite=true、onlyDeleted=false', async () => {
    const vm = useTestCaseManager();
    vm.favoriteOnly.value = true;
    await vm.refreshCurrentView();

    const params = lastGetAllParams();
    expect(params.favorite).toBe(true);
    expect(params.onlyDeleted).toBe(false);
  });

  it('标签视图：同样贯通 favorite/onlyDeleted（原先漏传致回收站断链）', async () => {
    const vm = useTestCaseManager();
    vm.viewMode.value = ViewMode.TAG;
    await nextTick();
    vm.favoriteOnly.value = true;
    await vm.refreshCurrentView();

    const params = lastTagViewParams();
    expect(params.favorite).toBe(true);
    expect(params.onlyDeleted).toBe(false);
  });

  it('回收站态：onlyDeleted=true 且 favorite 恒为 false（互斥口径）', async () => {
    const vm = useTestCaseManager();
    vm.favoriteOnly.value = true;
    vm.trashMode.value = true;
    await vm.refreshCurrentView();

    const params = lastGetAllParams();
    expect(params.onlyDeleted).toBe(true);
    expect(params.favorite).toBe(false);
  });
});

describe('toggleTrashMode：回收站切换联动', () => {
  it('进入回收站：trashMode 置位、收藏筛选清空、按回收站口径刷新', async () => {
    const vm = useTestCaseManager();
    vm.favoriteOnly.value = true;
    await vm.toggleTrashMode();

    expect(vm.trashMode.value).toBe(true);
    expect(vm.favoriteOnly.value).toBe(false);
    const params = lastGetAllParams();
    expect(params.onlyDeleted).toBe(true);
    expect(params.favorite).toBe(false);
  });

  it('视图切换到标签视图时按当前口径重取（watch 视图切换）', async () => {
    const vm = useTestCaseManager();
    vm.trashMode.value = true;
    vm.viewMode.value = ViewMode.TAG;

    await vi.waitFor(() => expect(ports.getTagView).toHaveBeenCalled());
    const params = lastTagViewParams();
    expect(params.onlyDeleted).toBe(true);
  });
});

describe('handleFavoriteToggle：星标切换与就地回写', () => {
  it('收藏成功：调 favoritesApi、patch 行数据 isFavorite、反馈「已收藏」', async () => {
    const vm = useTestCaseManager();
    await vm.refreshCurrentView(); // 填充空列表
    await vm.handleFavoriteToggle({ id: 'c1', name: 'case1' });

    expect(favoritesApi.favorite).toHaveBeenCalledWith('testcase', 'c1');
    const [message, type] = show.mock.calls[0];
    expect(type).toBe('success');
    expect(message).toBe('已收藏');
  });

  it('收藏失败：错误反馈', async () => {
    const vm = useTestCaseManager();
    favoritesApi.favorite.mockRejectedValueOnce(new Error('net down'));
    await vm.handleFavoriteToggle({ id: 'c1', name: 'case1' });

    const [message, type] = show.mock.calls[0];
    expect(type).toBe('error');
    expect(String(message)).toContain('收藏操作失败');
  });
});

describe('handleRestoreCase / handlePurgeCase：count 判真反馈（INT-215）', () => {
  it('restore：count>0 成功反馈并刷新当前视图', async () => {
    const vm = useTestCaseManager();
    favoritesApi.restore.mockResolvedValue({ restored_count: 1 });
    await vm.handleRestoreCase({ id: 'd1', name: 'deleted1' });

    expect(favoritesApi.restore).toHaveBeenCalledWith('testcase', ['d1']);
    const [message, type] = show.mock.calls[0];
    expect(type).toBe('success');
    expect(String(message)).toContain('已恢复');
    expect(ports.getAll).toHaveBeenCalled(); // 刷新
  });

  it('restore：count=0 提示无可恢复项（非假成功）', async () => {
    const vm = useTestCaseManager();
    favoritesApi.restore.mockResolvedValue({ restored_count: 0 });
    await vm.handleRestoreCase({ id: 'd1', name: 'deleted1' });

    const [message, type] = show.mock.calls[0];
    expect(type).toBe('info');
    expect(String(message)).toContain('无可恢复项');
  });

  it('purge：BASIC_CONFIRM（danger）确认后按 purged_count 判真', async () => {
    const vm = useTestCaseManager();
    modal.open.mockResolvedValue(true);
    favoritesApi.purge.mockResolvedValue({ purged_count: 1 });
    await vm.handlePurgeCase({ id: 'd1', name: 'deleted1' });

    expect(modal.open).toHaveBeenCalledWith('basicConfirm', expect.objectContaining({
      title: '彻底删除用例', danger: true,
    }));
    const [message, type] = show.mock.calls[0];
    expect(type).toBe('success');
    expect(String(message)).toContain('已彻底删除');
  });

  it('purge：count=0 提示无可删除项', async () => {
    const vm = useTestCaseManager();
    modal.open.mockResolvedValue(true);
    favoritesApi.purge.mockResolvedValue({ purged_count: 0 });
    await vm.handlePurgeCase({ id: 'd1', name: 'deleted1' });

    const [message, type] = show.mock.calls[0];
    expect(type).toBe('info');
    expect(String(message)).toContain('无可删除项');
  });

  it('purge：用户取消确认不发起请求', async () => {
    const vm = useTestCaseManager();
    modal.open.mockResolvedValue(false);
    await vm.handlePurgeCase({ id: 'd1', name: 'deleted1' });

    expect(modal.open).toHaveBeenCalled();
    expect(favoritesApi.purge).not.toHaveBeenCalled();
  });
});

describe('restoreAllTrash：全部恢复按后端圈定集合（INT-215 P2 回归）', () => {
  it('按 onlyDeleted 过滤取已删 id 集合，确认文案携带数量，恢复后判真反馈', async () => {
    const vm = useTestCaseManager();
    ports.getIdsByFilter.mockResolvedValue({ ids: ['a', 'b', 'c'] });
    favoritesApi.restore.mockResolvedValue({ restored_count: 3 });
    modal.open.mockResolvedValue(true);

    await vm.restoreAllTrash();

    expect(ports.getIdsByFilter).toHaveBeenCalledWith(expect.objectContaining({ onlyDeleted: true }));
    expect(modal.open).toHaveBeenCalledWith('basicConfirm', expect.objectContaining({
      title: '全部恢复',
    }));
    const options = modal.open.mock.calls[0][1];
    expect(options.content).toContain('3');
    expect(favoritesApi.restore).toHaveBeenCalledWith('testcase', ['a', 'b', 'c']);
    const [message, type] = show.mock.calls[0];
    expect(type).toBe('success');
    expect(String(message)).toContain('3');
  });

  it('回收站为空：直接提示，不弹确认、不发起恢复', async () => {
    const vm = useTestCaseManager();
    ports.getIdsByFilter.mockResolvedValue({ ids: [] });

    await vm.restoreAllTrash();

    const [message, type] = show.mock.calls[0];
    expect(type).toBe('info');
    expect(String(message)).toContain('回收站为空');
    expect(modal.open).not.toHaveBeenCalled();
    expect(favoritesApi.restore).not.toHaveBeenCalled();
  });

  it('恢复请求失败：错误反馈', async () => {
    const vm = useTestCaseManager();
    ports.getIdsByFilter.mockResolvedValue({ ids: ['a'] });
    favoritesApi.restore.mockRejectedValue(new Error('net down'));
    modal.open.mockResolvedValue(true);

    await vm.restoreAllTrash();

    const [message, type] = show.mock.calls[0];
    expect(type).toBe('error');
    expect(String(message)).toContain('恢复失败');
  });
});

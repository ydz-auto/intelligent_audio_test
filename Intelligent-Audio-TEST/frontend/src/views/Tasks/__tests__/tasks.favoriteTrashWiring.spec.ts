/**
 * INT-216：任务页收藏 / 回收站协调层单测（tasks.ts，INT-141/INT-215 新逻辑锁定）。
 *
 * 采用真实 useTaskList / useFavorites / useTask* 组合 + Infrastructure 端口层 mock
 * （http client / socket / vue-router / 模态），在 http 层断言查询参数，
 * 端到端锁定「视图切换口径 → fetch 参数 → wire 契约」贯通：
 * - toggleTaskTrashMode：status='deleted' 承载、deleted=true 下发、favoriteOnly 互斥、选中集清空
 * - handleTaskAction：favorite 反馈、restore/purge 按 restored_count/purged_count 判真（INT-215）
 * - purge/batchPurge：BASIC_CONFIRM 模态确认（不可恢复 + 权限警示），取消不调 purge
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

const http = vi.hoisted(() => ({ request: vi.fn() }));
const modal = vi.hoisted(() => ({ open: vi.fn() }));

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/utils/socket', () => ({
  default: { connect: vi.fn(), disconnect: vi.fn(), on: vi.fn(), off: vi.fn(), emit: vi.fn() },
}));

vi.mock('@/infrastructure/http/client', () => ({
  request: http.request,
  apiBaseUrl: '',
  addRequestInterceptor: vi.fn(),
  addResponseInterceptor: vi.fn(),
}));

vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({ open: modal.open }),
  MODAL_TYPES: { BASIC_CONFIRM: 'basicConfirm', DELETE_CONFIRM: 'deleteConfirm' },
}));

import { provideNotification } from '@/composables/modal/useNotification';
import { useTasks } from '../tasks';

const show = vi.fn();

/** 空列表 / 空统计响应（分页形状） */
const EMPTY_PAGE = { items: [], total: 0, page: 1, per_page: 10, pages: 1 };
const EMPTY_STATS = {
  total: 0, deleted_total: 0, status_counts: {}, type_counts: {},
  trend: [], granularity: 'day',
};

/** 找出对 /tasks 的最近一次 GET 查询参数 */
const lastTasksQuery = () => {
  const calls = http.request.mock.calls.filter(([, url]: any[]) => url === '/tasks');
  return calls[calls.length - 1]?.[3]?.params as Record<string, any>;
};

beforeEach(() => {
  vi.clearAllMocks();
  setActivePinia(createPinia());
  provideNotification({ show });
  http.request.mockImplementation((_method: string, url: string) => {
    if (url === '/tasks/stats') return Promise.resolve(EMPTY_STATS);
    return Promise.resolve(EMPTY_PAGE);
  });
});

describe('toggleTaskTrashMode：回收站切换口径（INT-215）', () => {
  it('进入回收站：filters.status=deleted、deleted=true 下发、选中集清空', async () => {
    const vm = useTasks();
    await vm.fetchTasks();
    http.request.mockClear();

    vm.selectedTasks.value.add(101);
    await vm.toggleTaskTrashMode();

    expect(vm.filters.value.status).toBe('deleted');
    expect(vm.selectedTasks.value.size).toBe(0);
    const params = lastTasksQuery();
    expect(params.deleted).toBe(true);   // INT-216 回归：此前映射缺失被静默丢弃
    expect(params.favorite).toBeUndefined();
  });

  it('进入回收站清空收藏筛选（互斥联动，favorite 不随 deleted 下发）', async () => {
    const vm = useTasks();
    vm.favoriteOnly.value = true;
    await vm.toggleTaskTrashMode();

    expect(vm.favoriteOnly.value).toBe(false);
    const params = lastTasksQuery();
    expect(params.deleted).toBe(true);
    expect(params.favorite).toBeUndefined();
  });

  it('退出回收站：恢复普通列表（无 deleted/favorite）', async () => {
    const vm = useTasks();
    await vm.toggleTaskTrashMode();
    await vm.toggleTaskTrashMode();

    expect(vm.filters.value.status).toBe('');
    const params = lastTasksQuery();
    expect(params.deleted).toBeUndefined();
    expect(params.favorite).toBeUndefined();
  });
});

describe('handleTaskFavoriteFilterChange：仅看收藏', () => {
  it('开启后 favorite=true 下发（仅收藏过滤贯通，INT-216 回归）', async () => {
    const vm = useTasks();
    await vm.handleTaskFavoriteFilterChange(true);

    expect(vm.favoriteOnly.value).toBe(true);
    const params = lastTasksQuery();
    expect(params.favorite).toBe(true);
    expect(params.deleted).toBeUndefined();
  });
});

describe('handleTaskAction：收藏 / 恢复 / 彻底删除', () => {
  it('favorite：toggle 后按 isFavorite 反馈「已收藏」', async () => {
    const vm = useTasks();
    http.request.mockImplementation((_m: string, url: string) =>
      url === '/tasks/7/favorite' ? Promise.resolve({ entity_id: '7' }) : Promise.resolve(EMPTY_PAGE));

    await vm.handleTaskAction({ action: 'favorite', task: { id: 7, name: 't7' } });

    expect(show).toHaveBeenCalledWith('已收藏', 'success', '');
  });

  it('favorite 失败：错误反馈且不误报成功', async () => {
    const vm = useTasks();
    http.request.mockImplementation((_m: string, url: string) =>
      url === '/tasks/7/favorite' ? Promise.reject(new Error('boom')) : Promise.resolve(EMPTY_PAGE));

    await vm.handleTaskAction({ action: 'favorite', task: { id: 7, name: 't7' } });

    const [message, type] = show.mock.calls.find(([m]: any[]) => String(m).startsWith('收藏操作失败'))!;
    expect(type).toBe('error');
    expect(String(message)).toContain('boom');
  });

  it('restore：restored_count>0 成功反馈并刷新；count=0 提示无可恢复项（判真反馈）', async () => {
    const vm = useTasks();
    http.request.mockImplementation((_m: string, url: string) =>
      url === '/tasks/restore' ? Promise.resolve({ restored_count: 1 }) : Promise.resolve(EMPTY_PAGE));

    await vm.handleTaskAction({ action: 'restore', task: { id: 9, name: 't9' } });
    const success = show.mock.calls.find(([m]: any[]) => String(m).includes('已恢复'));
    expect(success?.[1]).toBe('success');

    http.request.mockImplementation((_m: string, url: string) =>
      url === '/tasks/restore' ? Promise.resolve({ restored_count: 0 }) : Promise.resolve(EMPTY_PAGE));
    show.mockClear();
    await vm.handleTaskAction({ action: 'restore', task: { id: 9, name: 't9' } });
    const info = show.mock.calls.find(([m]: any[]) => String(m).includes('无可恢复'));
    expect(info?.[1]).toBe('info');
  });

  it('purge：BASIC_CONFIRM（danger + 不可恢复警示）确认后按 purged_count 判真', async () => {
    const vm = useTasks();
    modal.open.mockResolvedValue(true);
    http.request.mockImplementation((_m: string, url: string) =>
      url === '/tasks/purge' ? Promise.resolve({ purged_count: 1 }) : Promise.resolve(EMPTY_PAGE));

    await vm.handleTaskAction({ action: 'purge', task: { id: 3, name: 't3' } });

    expect(modal.open).toHaveBeenCalledWith('basicConfirm', expect.objectContaining({
      title: '彻底删除任务', danger: true,
    }));
    const [message, type] = show.mock.calls.find(([m]: any[]) => String(m).includes('已彻底删除'))!;
    expect(type).toBe('success');
    expect(String(message)).toContain('t3');
  });

  it('purge：count=0 提示无可删除项（权限不足可见，非假成功）', async () => {
    const vm = useTasks();
    modal.open.mockResolvedValue(true);
    http.request.mockImplementation((_m: string, url: string) =>
      url === '/tasks/purge' ? Promise.resolve({ purged_count: 0 }) : Promise.resolve(EMPTY_PAGE));

    await vm.handleTaskAction({ action: 'purge', task: { id: 3, name: 't3' } });

    const [message, type] = show.mock.calls.find(([m]: any[]) => String(m).includes('无可删除项'))!;
    expect(type).toBe('info');
  });

  it('purge：用户取消确认不发起请求', async () => {
    const vm = useTasks();
    modal.open.mockResolvedValue(false);

    await vm.handleTaskAction({ action: 'purge', task: { id: 3, name: 't3' } });

    expect(modal.open).toHaveBeenCalled();
    expect(http.request.mock.calls.some(([, url]: any[]) => url === '/tasks/purge')).toBe(false);
  });
});

describe('batchPurge：批量彻底删除（INT-215 批量口径）', () => {
  it('无选中不弹确认模态', async () => {
    const vm = useTasks();
    await vm.batchPurge();
    expect(modal.open).not.toHaveBeenCalled();
  });

  it('确认后按选中集全量 purge，成功清空选中并反馈数量', async () => {
    const vm = useTasks();
    await vm.fetchTasks();
    vm.selectedTasks.value.add('a');
    vm.selectedTasks.value.add('b');
    modal.open.mockResolvedValue(true);
    http.request.mockImplementation((_m: string, url: string) =>
      url === '/tasks/purge' ? Promise.resolve({ purged_count: 2 }) : Promise.resolve(EMPTY_PAGE));

    await vm.batchPurge();

    expect(modal.open).toHaveBeenCalledWith('basicConfirm', expect.objectContaining({
      title: '批量彻底删除任务', danger: true,
    }));
    const purgeCall = http.request.mock.calls.find(([, url]: any[]) => url === '/tasks/purge');
    expect(purgeCall?.[2]).toEqual({ ids: ['a', 'b'] });
    expect(vm.selectedTasks.value.size).toBe(0);
    const [message, type] = show.mock.calls.find(([m]: any[]) => String(m).includes('已彻底删除'))!;
    expect(type).toBe('success');
    expect(String(message)).toContain('2');
  });

  it('purged_count=0 提示无可删除项（非假成功），随后仍清空选中并刷新列表', async () => {
    const vm = useTasks();
    await vm.fetchTasks();
    vm.selectedTasks.value.add('a');
    modal.open.mockResolvedValue(true);
    http.request.mockImplementation((_m: string, url: string) =>
      url === '/tasks/purge' ? Promise.resolve({ purged_count: 0 }) : Promise.resolve(EMPTY_PAGE));

    await vm.batchPurge();

    const [message, type] = show.mock.calls.find(([m]: any[]) => String(m).includes('无可删除项'))!;
    expect(type).toBe('info');
    expect(vm.selectedTasks.value.size).toBe(0);
    // count=0 仍触发列表刷新（回收站数据集可能已被他人变化）
    expect(lastTasksQuery()).toBeDefined();
  });
});

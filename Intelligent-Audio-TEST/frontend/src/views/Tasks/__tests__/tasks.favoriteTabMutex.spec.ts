/**
 * INT-320：收藏页签绕过回收站互斥修复——「两案并举」回归锁定。
 *
 * 缺陷（INT-298 引入）：日常页签处于回收站态（filters.status='deleted'）时
 * 切入「收藏」页签，watch → loadFavoriteView 仅设 favoriteOnly=true，
 * useTaskList.send 侧只判 favoriteOnly → favorite=true 与 deleted=true 双参数并发，
 * 文档《收藏回收站操作人交互规范设计文档》§3.3 互斥不变量在页签路径上失效；
 * 反向切回日常页签时 taskTrashMode 仍为 true，FavoriteTrashBar 回显回收站态不对称。
 *
 * 规划师裁定（两案并举，本 spec 锁定两层防线）：
 * ① 发送侧守卫（useTaskList）：仅 favoriteOnly && filters.status!=='deleted' 才携带
 *    favorite=true——互斥不依赖入口清空顺序（对齐报告/用例侧口径）；
 * ② 入口清空（tasks.ts 协调层 loadFavoriteView）：进入收藏页签时回收站态还原为 ''，
 *    leaveFavoriteView 对称还原（对齐 toggleTaskTrashMode 清空语义，UI 回显对称）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

const http = vi.hoisted(() => ({ request: vi.fn() }));

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

import { provideNotification } from '@/composables/modal/useNotification';
import { useTaskList } from '@/composables/task/useTaskList';
import { useTasks } from '../tasks';

const show = vi.fn();

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

describe('发送侧守卫（useTaskList，防线②：互斥不依赖入口顺序）', () => {
  it('回收站态下 favoriteOnly=true 也不携带 favorite（仅 deleted=true）', async () => {
    const vm = useTaskList();
    vm.filters.value.status = 'deleted';
    vm.favoriteOnly.value = true;
    await vm.fetchTasks();

    const params = lastTasksQuery();
    expect(params.deleted).toBe(true);
    expect(params.favorite).toBeUndefined();
  });

  it('非回收站态下 favoriteOnly=true 正常携带 favorite=true（守卫不误伤）', async () => {
    const vm = useTaskList();
    vm.filters.value.status = '';
    vm.favoriteOnly.value = true;
    await vm.fetchTasks();

    const params = lastTasksQuery();
    expect(params.favorite).toBe(true);
    expect(params.deleted).toBeUndefined();
  });

  it('回收站态且 favoriteOnly=false：仅 deleted=true（基线回归）', async () => {
    const vm = useTaskList();
    vm.filters.value.status = 'deleted';
    vm.favoriteOnly.value = false;
    await vm.fetchTasks();

    const params = lastTasksQuery();
    expect(params.deleted).toBe(true);
    expect(params.favorite).toBeUndefined();
  });
});

describe('收藏页签进出（tasks.ts 协调层，防线①：入口清空对称）', () => {
  it('回收站态进入收藏页签：filters.status 还原为空 + favorite=true 下发（无 deleted）', async () => {
    const vm = useTasks();
    await vm.toggleTaskTrashMode();
    http.request.mockClear();

    await vm.loadFavoriteView();

    expect(vm.filters.value.status).toBe('');
    expect(vm.favoriteOnly.value).toBe(true);
    const params = lastTasksQuery();
    expect(params.favorite).toBe(true);
    expect(params.deleted).toBeUndefined();
  });

  it('普通态进入收藏页签：仅追加 favorite=true，不清日常筛选（守卫不误伤入口）', async () => {
    const vm = useTasks();
    vm.filters.value.status = 'completed';
    http.request.mockClear();

    await vm.loadFavoriteView();

    expect(vm.filters.value.status).toBe('completed');
    const params = lastTasksQuery();
    expect(params.favorite).toBe(true);
    expect(params.deleted).toBeUndefined();
  });

  it('验收口径：回收站态→收藏→日常往返后，favorite/deleted 双双不携带（对称还原）', async () => {
    const vm = useTasks();
    await vm.toggleTaskTrashMode();
    await vm.loadFavoriteView();
    await vm.leaveFavoriteView();

    expect(vm.favoriteOnly.value).toBe(false);
    expect(vm.taskTrashMode.value).toBe(false);  // 反向回显对称：FavoriteTrashBar 不再亮回收站
    const params = lastTasksQuery();
    expect(params.favorite).toBeUndefined();
    expect(params.deleted).toBeUndefined();
  });

  it('未进收藏页签时 leaveFavoriteView 幂等不触发刷新', async () => {
    const vm = useTasks();
    await vm.fetchTasks();
    http.request.mockClear();

    await vm.leaveFavoriteView();

    expect(lastTasksQuery()).toBeUndefined();
  });
});

describe('工具栏口径不回退（toggleTaskTrashMode 既有互斥语义回归）', () => {
  it('收藏态进入回收站仍清空勾选且 favorite 不随 deleted 下发', async () => {
    const vm = useTasks();
    vm.favoriteOnly.value = true;
    await vm.toggleTaskTrashMode();

    expect(vm.favoriteOnly.value).toBe(false);
    const params = lastTasksQuery();
    expect(params.deleted).toBe(true);
    expect(params.favorite).toBeUndefined();
  });
});

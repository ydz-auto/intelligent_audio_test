/**
 * INT-1300：任务页「创建新任务」入口贯通单测（任务类型概念移除后）。
 *
 * 负责人 2026-10-22 口径：「不分 API/E2E 测试，前端如有相关概念一律移除」。
 * 原 INT-309 的双层断点（TaskTypeModal emit 载荷键 / handleCreateTask 分发 /
 * /APITest·/E2ETest 路由注册）已随任务类型选择弹窗整体移除——创建新任务不再
 * 弹类型选择，直接 push 到已注册的 /start-test 单流程（E2E+API 合并入口）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

const pushes = vi.hoisted(() => ({ list: [] as any[] }));

// 仅替换 useRouter（tasks.ts 协调层注入点）；createRouter/createWebHashHistory
// 保持原实现，供真实路由表存在性断言使用
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>();
  return { ...actual, useRouter: () => ({ push: (loc: any) => pushes.list.push(loc) }) };
});

vi.mock('@/utils/socket', () => ({
  default: { connect: vi.fn(), disconnect: vi.fn(), on: vi.fn(), off: vi.fn(), emit: vi.fn() },
}));

const http = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('@/infrastructure/http/client', () => ({
  request: http.request,
  apiBaseUrl: '',
  addRequestInterceptor: vi.fn(),
  addResponseInterceptor: vi.fn(),
}));

vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({ open: vi.fn() }),
  MODAL_TYPES: { BASIC_CONFIRM: 'basicConfirm' },
}));

import { provideNotification } from '@/composables/modal/useNotification';
import { useTasks } from '../tasks';
// 真实路由表（断言 /start-test 已注册，不再落 404 兜底）
import router from '@/router';

const show = vi.fn();

const EMPTY_PAGE = { items: [], total: 0, page: 1, per_page: 10, pages: 1 };
const EMPTY_STATS = {
  total: 0, deleted_total: 0, status_counts: {}, type_counts: {},
  trend: [], granularity: 'day',
};

beforeEach(() => {
  vi.clearAllMocks();
  pushes.list.length = 0;
  setActivePinia(createPinia());
  provideNotification({ show });
  http.request.mockImplementation((_method: string, url: string) => {
    if (url === '/tasks/stats') return Promise.resolve(EMPTY_STATS);
    return Promise.resolve(EMPTY_PAGE);
  });
});

describe('createNewTask 直接进 /start-test（INT-1300：任务类型概念移除）', () => {
  it('点「创建新任务」→ 直接 push /start-test，无类型选择弹窗', () => {
    const vm = useTasks();
    vm.createNewTask();
    expect(pushes.list).toEqual(['/start-test']);
  });

  it('不再暴露任务类型弹窗状态与分发（isTaskTypeModalVisible / handleCreateTask 已移除）', () => {
    const vm = useTasks();
    expect((vm as any).isTaskTypeModalVisible).toBeUndefined();
    expect((vm as any).handleCreateTask).toBeUndefined();
  });
});

describe('跳转目标路由存在性（/start-test 已注册，非 404 兜底）', () => {
  it('/start-test 已注册且 name=startTest', () => {
    const resolved = router.resolve('/start-test');
    expect(resolved.matched).toHaveLength(1);
    expect(resolved.name).toBe('startTest');
  });
});

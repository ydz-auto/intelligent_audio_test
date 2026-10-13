/**
 * INT-309：任务页「创建新任务」入口贯通单测（双层断点回归锁定）。
 *
 * 原断点（静态证据，均已修复）：
 * 1. TaskTypeModal emit 载荷键 `testTestType` vs handleCreateTask 读 `data.testType`
 *    → 恒 undefined → 两个 router.push 分支都不进（静默无操作）；
 * 2. 跳转目标 `/create-api-task`、`/create-e2e-task` 路由未注册 → 落 404 兜底。
 *
 * 锁定口径（选项 1，对齐 INT-265 手册 B3'——跳测试页五步向导，不新注册路由）：
 * - TaskTypeModal confirm 载荷键为 testType，值 'APITest' / 'E2ETest'；
 * - handleCreateTask 按载荷键分发，push 到已注册路由 /APITest、/E2ETest；
 * - 目标路由在真实路由表（router/index.ts）中存在，任务页与测试页权限一致
 *   （task:execute，任务页读者可进）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
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
  MODAL_TYPES: { BASIC_CONFIRM: 'basicConfirm', TASK_RELATED: 'taskTypeSelect' },
}));

import TaskTypeModal from '@/components/common/modal/TaskTypeModal.vue';
import { provideNotification } from '@/composables/modal/useNotification';
import { useTasks } from '../tasks';
// 真实路由表（断言目标路由已注册，不再落 404 兜底）
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

describe('TaskTypeModal confirm 载荷键与值（INT-309 #1：emit 键对齐）', () => {
  const mountModal = () =>
    mount(TaskTypeModal, { props: { modalId: 'task-type-modal' } });

  it('点「API测试」→ confirm 载荷键为 testType（非 testTestType）、值为 APITest', async () => {
    const w = mountModal();
    await w.findAll('.task-type-btn').find(b => b.text().includes('API测试'))!.trigger('click');
    const payload = w.emitted('confirm')![0][0] as Record<string, any>;
    expect(payload).toHaveProperty('testType', 'APITest');
    expect(payload).not.toHaveProperty('testTestType');
  });

  it('点「端到端测试」→ confirm 载荷键为 testType、值为 E2ETest', async () => {
    const w = mountModal();
    await w.findAll('.task-type-btn').find(b => b.text().includes('端到端测试'))!.trigger('click');
    const payload = w.emitted('confirm')![0][0] as Record<string, any>;
    expect(payload).toHaveProperty('testType', 'E2ETest');
    expect(payload).not.toHaveProperty('testTestType');
  });

  it('点击不再调用 ModalManager 不存在的 confirm 方法（原 TypeError 断点）', async () => {
    const w = mountModal();
    await w.findAll('.task-type-btn')[0].trigger('click');
    // 无未捕获异常即通过（原实现 modalManager.confirm 抛 TypeError）
    expect(w.emitted('confirm')).toHaveLength(1);
  });
});

describe('handleCreateTask 分发（INT-309 #2：读取载荷键并跳已注册路由）', () => {
  it('testType=APITest → push /APITest 并关闭弹窗', async () => {
    const vm = useTasks();
    vm.createNewTask();
    expect(vm.isTaskTypeModalVisible.value).toBe(true);

    await vm.handleCreateTask({ testType: 'APITest' });
    expect(vm.isTaskTypeModalVisible.value).toBe(false);
    expect(pushes.list).toEqual(['/APITest']);
  });

  it('testType=E2ETest → push /E2ETest 并关闭弹窗', async () => {
    const vm = useTasks();
    await vm.handleCreateTask({ testType: 'E2ETest' });
    expect(pushes.list).toEqual(['/E2ETest']);
  });

  it('旧拼写键 testTestType 不触发跳转（防止回归回退到静默失效）', async () => {
    const vm = useTasks();
    await vm.handleCreateTask({ testTestType: 'APITest' } as any);
    expect(pushes.list).toEqual([]);
  });
});

describe('跳转目标路由存在性（INT-309：真实路由表核对，不再落 404 兜底）', () => {
  it('/APITest 与 /E2ETest 均已注册且非 404 兜底', () => {
    for (const path of ['/APITest', '/E2ETest']) {
      const resolved = router.resolve(path);
      expect(resolved.matched).toHaveLength(1);
      expect(resolved.name).not.toBe('notFound');
    }
  });

  it('目标路由权限为 task:execute（与导航栏测试页入口一致）', () => {
    expect(router.resolve('/APITest').meta.permission).toBe('task:execute');
    expect(router.resolve('/E2ETest').meta.permission).toBe('task:execute');
  });
});

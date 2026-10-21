/**
 * INT-273：任务类型筛选（api/e2e/mixed）——useTaskList 下发 taskType 参数，
 * 经 tasksApi 转换层 snake_case 化为 task_type（DTO 契约）。
 *
 * 锁定口径：
 * - filters.type 非空且非 'all' 时下发 taskType → HTTP query task_type
 * - 'all' / '' 归一为空串，不下发 task_type
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

const http = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock('@/utils/socket', () => ({
  default: { connect: vi.fn(), disconnect: vi.fn(), on: vi.fn(), off: vi.fn(), emit: vi.fn() },
}));

vi.mock('@/infrastructure/http/client', () => ({
  request: http.request,
  apiBaseUrl: '',
  addRequestInterceptor: vi.fn(),
  addResponseInterceptor: vi.fn(),
}));

import { useTaskList } from '../useTaskList';

const EMPTY_PAGE = { items: [], total: 0, page: 1, per_page: 10, pages: 1 };
const EMPTY_STATS = {
  total: 0, deleted_total: 0, status_counts: {}, type_counts: {},
  trend: [], granularity: 'day',
};

const lastTasksQuery = () => {
  const calls = http.request.mock.calls.filter(([, url]: any[]) => url === '/tasks');
  return calls[calls.length - 1]?.[3]?.params as Record<string, any>;
};

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
  http.request.mockImplementation((_method: string, url: string) => {
    if (url === '/tasks/stats') return Promise.resolve(EMPTY_STATS);
    return Promise.resolve(EMPTY_PAGE);
  });
});

describe('任务类型筛选参数下发（INT-273）', () => {
  it('filters.type=e2e 下发 task_type=e2e', async () => {
    const vm = useTaskList();
    vm.filters.value.type = 'e2e';
    await vm.fetchTasks();

    const params = lastTasksQuery();
    expect(params.task_type).toBe('e2e');
  });

  it('filters.type=mixed 下发 task_type=mixed', async () => {
    const vm = useTaskList();
    vm.filters.value.type = 'mixed';
    await vm.fetchTasks();

    const params = lastTasksQuery();
    expect(params.task_type).toBe('mixed');
  });

  it('type 为 all 归一为空串，不下发 task_type', async () => {
    const vm = useTaskList();
    vm.filters.value.type = 'all';
    await vm.fetchTasks();

    const params = lastTasksQuery();
    expect(params.task_type).toBeUndefined();
  });

  it('type 为空串，不下发 task_type', async () => {
    const vm = useTaskList();
    await vm.fetchTasks();

    const params = lastTasksQuery();
    expect(params.task_type).toBeUndefined();
  });

  it('类型筛选与执行/评估筛选叠加下发（AND 语义）', async () => {
    const vm = useTaskList();
    vm.filters.value.type = 'api';
    vm.filters.value.status = 'completed';
    vm.filters.value.evaluationStatus = 'failed';
    await vm.fetchTasks();

    const params = lastTasksQuery();
    expect(params.task_type).toBe('api');
    expect(params.execution_status).toBe('completed');
    expect(params.evaluation_status).toBe('failed');
  });
});

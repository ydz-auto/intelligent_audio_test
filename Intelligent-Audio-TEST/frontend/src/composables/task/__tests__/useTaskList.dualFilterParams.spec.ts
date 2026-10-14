/**
 * INT-301 F1（UX 审计打回）：执行状态筛选改走 execution_status 派生参数。
 *
 * 锁定口径：
 * - useTaskList 执行筛选（filters.status，回收站 'deleted' 除外）下发
 *   executionStatus 参数（命中行执行徽章 == 筛选值），不再按原始 status 裸匹配
 * - 评估筛选继续下发 evaluationStatus
 * - 回收站态仍走 deleted=true，不带执行/评估参数
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

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
  vi.clearAllMocks();
  http.request.mockImplementation((_method: string, url: string) => {
    if (url === '/tasks/stats') return Promise.resolve(EMPTY_STATS);
    return Promise.resolve(EMPTY_PAGE);
  });
});

describe('执行/评估筛选参数下发（INT-301 F1）', () => {
  it('执行筛选 completed 下发 execution_status=completed（派生口径），不下发原始 status', async () => {
    const vm = useTaskList();
    vm.filters.value.status = 'completed';
    await vm.fetchTasks();

    const params = lastTasksQuery();
    expect(params.execution_status).toBe('completed');
    expect(params.status).toBeUndefined();
  });

  it('评估筛选 evaluating 下发 evaluation_status=evaluating', async () => {
    const vm = useTaskList();
    vm.filters.value.evaluationStatus = 'evaluating';
    await vm.fetchTasks();

    const params = lastTasksQuery();
    expect(params.evaluation_status).toBe('evaluating');
  });

  it('双筛选叠加：execution_status 与 evaluation_status 并存（AND 语义）', async () => {
    const vm = useTaskList();
    vm.filters.value.status = 'completed';
    vm.filters.value.evaluationStatus = 'failed';
    await vm.fetchTasks();

    const params = lastTasksQuery();
    expect(params.execution_status).toBe('completed');
    expect(params.evaluation_status).toBe('failed');
  });

  it('回收站态仍走 deleted=true，不带执行/评估参数（INT-141 口径不变）', async () => {
    const vm = useTaskList();
    vm.filters.value.status = 'deleted';
    await vm.fetchTasks();

    const params = lastTasksQuery();
    expect(params.deleted).toBe(true);
    expect(params.execution_status).toBeUndefined();
    expect(params.evaluation_status).toBeUndefined();
  });
});

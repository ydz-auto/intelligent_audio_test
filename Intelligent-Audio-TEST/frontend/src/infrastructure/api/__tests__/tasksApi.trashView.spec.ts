/**
 * INT-216 回归：任务模块收藏 / 回收站列表参数 wire 契约。
 *
 * 缺陷（本卡补测中发现）：useTaskList.fetchTasks 在回收站态设置 params.deleted=true、
 * 收藏筛选设置 params.favorite=true，但 toTaskListQueryDto 未映射这两个 key——
 * 参数在 Infrastructure 层被静默丢弃，任务页回收站显示活跃任务、仅看收藏静默失效
 * （对照后端 TaskListQuery.favorite/deleted 已支持：api_gateway/schemas/task.py）。
 * 锁定：camelCase → snake_case 查询参数映射不回退。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/infrastructure/http/client', () => ({
  request: vi.fn(),
  apiBaseUrl: '',
  addRequestInterceptor: vi.fn(),
  addResponseInterceptor: vi.fn(),
}));

import { request } from '@/infrastructure/http/client';
import { tasksApi } from '../tasksApi';

const mockedRequest = vi.mocked(request);

beforeEach(() => {
  mockedRequest.mockReset();
  mockedRequest.mockResolvedValue({ items: [], total: 0, page: 1, per_page: 10, pages: 1 });
});

describe('tasksApi 收藏 / 回收站参数契约（INT-216）', () => {
  it('getAll 映射 deleted=true（回收站态仅软删除项）', async () => {
    await tasksApi.getAll({ page: 1, perPage: 10, deleted: true });
    const params = mockedRequest.mock.calls[0][3]?.params as Record<string, any>;
    expect(params.deleted).toBe(true);
  });

  it('getAll 映射 favorite=true（仅当前用户收藏）', async () => {
    await tasksApi.getAll({ page: 1, perPage: 10, favorite: true });
    const params = mockedRequest.mock.calls[0][3]?.params as Record<string, any>;
    expect(params.favorite).toBe(true);
  });

  it('显式 false 不被丢弃（store 层兜底口径与 testcasesApi 一致）', async () => {
    await tasksApi.getAll({ page: 1, perPage: 10, favorite: false, deleted: false });
    const params = mockedRequest.mock.calls[0][3]?.params as Record<string, any>;
    expect(params.favorite).toBe(false);
    expect(params.deleted).toBe(false);
  });

  it('未传入时不产出 favorite/deleted 键（普通列表不带冗余过滤）', async () => {
    await tasksApi.getAll({ page: 1, perPage: 10 });
    const params = mockedRequest.mock.calls[0][3]?.params as Record<string, any>;
    expect(params).not.toHaveProperty('favorite');
    expect(params).not.toHaveProperty('deleted');
  });

  it('既有 snake_case 映射不回退（status/algorithmType/search/时间）', async () => {
    await tasksApi.getAll({
      page: 2, perPage: 20, status: 'completed', algorithmType: 'asr',
      search: 'kw', startTime: '2026-01-01', endTime: '2026-01-31',
    });
    const params = mockedRequest.mock.calls[0][3]?.params as Record<string, any>;
    expect(params).toEqual({
      page: 2,
      per_page: 20,
      status: 'completed',
      algorithm_type: 'asr',
      search: 'kw',
      start_date: '2026-01-01',
      end_date: '2026-01-31',
    });
  });
});

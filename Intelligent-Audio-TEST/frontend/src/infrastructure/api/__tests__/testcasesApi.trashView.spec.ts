/**
 * INT-215 回归：收藏 / 回收站过滤参数 wire 契约。
 *
 * 缺陷回归（P1/P2）：标签视图 fetchTagView 未透传 favorite/onlyDeleted，
 * 回收站 + 标签视图组合显示活跃用例（断链）；全部恢复的 ID 圈定
 * 需 only_deleted 贯通 /testcases/ids。锁定 Infrastructure 层
 * camelCase → snake_case 查询参数映射不被回退。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}));

import { request } from '../../http/client';
import { testcasesApi } from '../testcasesApi';

const mockedRequest = vi.mocked(request);

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('testcasesApi 收藏 / 回收站参数契约（INT-215）', () => {
  it('getTagView 透传 favorite 并映射 onlyDeleted→only_deleted、携带 view=tag', async () => {
    mockedRequest.mockResolvedValueOnce({ items: [], total: 0, page: 1, per_page: 50, pages: 1 });
    await testcasesApi.getTagView({ page: 1, perPage: 50, favorite: true, onlyDeleted: true });
    const [method, url, , options] = mockedRequest.mock.calls[0];
    expect(method).toBe('GET');
    expect(url).toBe('/testcases');
    const params = options?.params as Record<string, any>;
    expect(params.view).toBe('tag');
    expect(params.favorite).toBe(true);
    expect(params.only_deleted).toBe(true);
  });

  it('getTagView 显式 false 不被查询参数构建丢弃（store 层兜底 false 的前提）', async () => {
    mockedRequest.mockResolvedValueOnce({ items: [], total: 0, page: 1, per_page: 50, pages: 1 });
    await testcasesApi.getTagView({ page: 1, perPage: 50, favorite: false, onlyDeleted: false });
    const params = mockedRequest.mock.calls[0][3]?.params as Record<string, any>;
    expect(params.favorite).toBe(false);
    expect(params.only_deleted).toBe(false);
  });

  it('getAll 列表同样映射 onlyDeleted→only_deleted、favorite 透传', async () => {
    mockedRequest.mockResolvedValueOnce({ items: [], total: 0, page: 1, per_page: 50, pages: 1 });
    await testcasesApi.getAll({ page: 1, perPage: 50, favorite: true, onlyDeleted: true });
    const params = mockedRequest.mock.calls[0][3]?.params as Record<string, any>;
    expect(params.favorite).toBe(true);
    expect(params.only_deleted).toBe(true);
  });

  it('getIdsByFilter 请求体映射 onlyDeleted→only_deleted（回收站全部恢复圈定口径）', async () => {
    mockedRequest.mockResolvedValueOnce({ ids: ['a', 'b'] });
    const result = await testcasesApi.getIdsByFilter({ onlyDeleted: true, testType: 'api' });
    expect(mockedRequest).toHaveBeenCalledWith('POST', '/testcases/ids', { only_deleted: true, type: 'api' });
    expect(result.ids).toEqual(['a', 'b']);
  });
});

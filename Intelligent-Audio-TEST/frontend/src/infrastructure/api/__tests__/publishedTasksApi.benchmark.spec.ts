/**
 * publishedTasksApi Benchmark 字段契约测试
 * 覆盖：列表/详情 DTO 的 benchmark → camelCase Domain 映射、
 * publish 请求体以 snake_case 携带 benchmark / benchmark_suite / benchmark_category。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}));

import { request } from '../../http/client';
import { publishedTasksApi } from '../publishedTasksApi';

const mockedRequest = vi.mocked(request);

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('publishedTasksApi benchmark 契约', () => {
  it('列表项映射 benchmark 布尔（缺省回退 false）', async () => {
    mockedRequest.mockResolvedValueOnce({
      items: [
        { id: 1, name: 'A', type: 'e2e', status: 'published', benchmark: true, version: 1, is_current: true },
        { id: 2, name: 'B', type: 'api', status: 'published', version: 1, is_current: true },
      ],
      total: 2, page: 1, per_page: 10, pages: 1,
    });
    const page = await publishedTasksApi.getAll();
    expect(page.items[0].benchmark).toBe(true);
    expect(page.items[1].benchmark).toBe(false);
  });

  it('详情映射 benchmark 布尔', async () => {
    mockedRequest.mockResolvedValueOnce({
      id: 1, name: 'A', type: 'e2e', status: 'published', benchmark: true, version: 1, is_current: true,
      snapshot_config: { benchmarkSuite: 'suite-1', benchmarkCategory: 'tts' },
      has_report_snapshot: false, versions: [], execution_history: [],
    });
    const detail = await publishedTasksApi.getOne(1);
    expect(detail.benchmark).toBe(true);
    expect(detail.snapshotConfig.benchmarkSuite).toBe('suite-1');
    expect(detail.snapshotConfig.benchmarkCategory).toBe('tts');
  });

  it('publish 以 snake_case 透传 benchmark / benchmark_suite / benchmark_category', async () => {
    mockedRequest.mockResolvedValueOnce({ id: 9 });
    await publishedTasksApi.publish({
      sourceTaskId: 3, name: 'X', benchmark: true, benchmarkSuite: 'suite-1', benchmarkCategory: 'asr',
    });
    expect(mockedRequest).toHaveBeenCalledWith('POST', '/published-tasks', expect.objectContaining({
      source_task_id: 3,
      benchmark: true,
      benchmark_suite: 'suite-1',
      benchmark_category: 'asr',
    }));
  });

  it('未开启 benchmark 时请求体不携带分组字段', async () => {
    mockedRequest.mockResolvedValueOnce({ id: 9 });
    await publishedTasksApi.publish({ sourceTaskId: 3, name: 'X', benchmark: false });
    const body = mockedRequest.mock.calls[0][2] as Record<string, any>;
    expect(body.benchmark).toBe(false);
    expect(body.benchmark_suite).toBeUndefined();
    expect(body.benchmark_category).toBeUndefined();
  });
});

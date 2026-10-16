/**
 * INT-548 logsApi 归档 5 端点接线契约测试
 *
 * 断言 5 个归档方法都发出正确的 method/URL/请求体/参数，并复用 adapter 映射：
 *   GET    /logs/archive/status
 *   POST   /logs/archive
 *   GET    /logs/archive/logs
 *   GET    /logs/archive/{filename}   （blob 下载）
 *   DELETE /logs/archive/{filename}
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}));

import { request } from '../../http/client';
import { logsApi } from '../logsApi';

const mockedRequest = vi.mocked(request);

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('logsApi 归档 5 端点', () => {
  it('getArchiveStatus：GET /logs/archive/status → adapter 映射为 camelCase', async () => {
    mockedRequest.mockResolvedValue({
      totalLogs: 100,
      hotLogs: 60,
      coldLogs: 40,
      archiveDir: 'oss://archives',
      taskArchives: 3,
      caseArchives: 2,
      otherArchives: 1,
    });
    const result = await logsApi.getArchiveStatus();
    expect(mockedRequest).toHaveBeenCalledWith('GET', '/logs/archive/status', null, expect.anything());
    expect(result).toEqual({
      totalLogs: 100,
      hotLogs: 60,
      coldLogs: 40,
      archiveDir: 'oss://archives',
      taskArchives: 3,
      caseArchives: 2,
      otherArchives: 1,
    });
  });

  it('archive：POST /logs/archive，请求体 days/dry_run snake_case', async () => {
    mockedRequest.mockResolvedValue({ archived_count: 5, deleted_count: 5, remaining_count: 9 });
    const result = await logsApi.archive({ days: 30, dryRun: true });
    expect(mockedRequest).toHaveBeenCalledWith(
      'POST',
      '/logs/archive',
      { days: 30, dry_run: true },
      expect.anything(),
    );
    expect(result.archivedCount).toBe(5);
  });

  it('getArchivedLogs：GET /logs/archive/logs，参数 task_id/test_case_id', async () => {
    mockedRequest.mockResolvedValue({ items: [], total: 0, source: 'archive' });
    const result = await logsApi.getArchivedLogs({ taskId: 493, testCaseId: 'case-1' });
    expect(mockedRequest).toHaveBeenCalledWith('GET', '/logs/archive/logs', null, {
      params: { task_id: 493, test_case_id: 'case-1' },
    });
    expect(result.total).toBe(0);
  });

  it('downloadArchive：GET /logs/archive/{filename}，blob 响应', async () => {
    mockedRequest.mockResolvedValue('json-bytes');
    const result = await logsApi.downloadArchive('task_case/493/case-1/2026-10-15.json');
    expect(mockedRequest).toHaveBeenCalledWith(
      'GET',
      '/logs/archive/task_case%2F493%2Fcase-1%2F2026-10-15.json',
      null,
      expect.objectContaining({ responseType: 'blob' }),
    );
    expect(result).toBeTruthy();
  });

  it('deleteArchive：DELETE /logs/archive/{filename}', async () => {
    mockedRequest.mockResolvedValue(undefined);
    await logsApi.deleteArchive('task_case/493/case-1/2026-10-15.json');
    expect(mockedRequest).toHaveBeenCalledWith(
      'DELETE',
      '/logs/archive/task_case%2F493%2Fcase-1%2F2026-10-15.json',
      null,
      expect.anything(),
    );
  });
});

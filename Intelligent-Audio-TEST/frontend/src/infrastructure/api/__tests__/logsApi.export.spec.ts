/**
 * logsApi.export 契约测试（INT-274 审计 P2 修复）
 *
 * 审计发现：导出弹窗的 format/范围选择被后端静默忽略——前端走 GET 空 body，
 * 后端 LogExportRequest.model_validate(request.get_json() or {}) 落默认
 * format=excel、log_ids=None，弹窗默认「.json / 选中数据」与实际产出
 * （.xlsx / 全量）不符。
 *
 * 修复口径（doc/接口文档 6. 导出日志 本就声明 POST body 契约）：
 * 导出改 POST 携带 body——format/log_ids 真正到达后端；
 * Domain logIds 逗号串在 adapter 层转为后端期望的 int 数组。
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
  mockedRequest.mockResolvedValue({});
});

describe('logsApi.export POST 契约', () => {
  it('导出走 POST /logs/export，log_ids 逗号串转 int 数组、format 透传', async () => {
    await logsApi.export({ logIds: '1,2,3', format: 'json', level: 'error', module: 'exec' });

    expect(mockedRequest).toHaveBeenCalledTimes(1);
    const [method, url, body] = mockedRequest.mock.calls[0];
    expect(method).toBe('POST');
    expect(url).toBe('/logs/export');
    expect(body).toMatchObject({
      log_ids: [1, 2, 3],
      format: 'json',
      level: 'error',
      module: 'exec',
    });
  });

  it('范围=全部时不携带 log_ids，format 仍进入 body', async () => {
    await logsApi.export({ format: 'excel' });

    const [method, , body] = mockedRequest.mock.calls[0];
    expect(method).toBe('POST');
    expect(body).toEqual({ format: 'excel' });
    expect(body).not.toHaveProperty('log_ids');
  });

  it('过滤条件经 toLogQueryDto 转 snake_case 进 body（keyword/start_time 等）', async () => {
    await logsApi.export({
      keyword: 'timeout',
      startTime: '2026-10-01T00:00:00',
      endTime: '2026-10-02T00:00:00',
      logIds: '7',
      format: 'json',
    });

    const [, , body] = mockedRequest.mock.calls[0];
    expect(body).toMatchObject({
      keyword: 'timeout',
      start_time: '2026-10-01T00:00:00',
      end_time: '2026-10-02T00:00:00',
      log_ids: [7],
      format: 'json',
    });
  });
});

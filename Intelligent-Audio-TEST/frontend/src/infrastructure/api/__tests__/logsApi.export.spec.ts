/**
 * INT-1000 logsApi.export 导出契约测试（INT-274 契约同步到 wiring/ux-vue）
 *
 * 断言 export 改为 POST /logs/export + 请求体（log_ids int 数组 + format），
 * level/module 过滤走 query，响应为 blob（后端 FileResponse 原始文件流）。
 * 旧实现 GET + query 流程与后端契约错位：GET 空 body → 后端恒返回 Excel、
 * 选中范围/格式被忽略、client.ts 以 json 解析二进制抛「Server returned invalid JSON」。
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

describe('logsApi.export（POST /logs/export，INT-274 契约）', () => {
  it('导出全部：POST 请求体 format + query level/module，blob 响应', async () => {
    mockedRequest.mockResolvedValue('json-bytes');
    await logsApi.export({ level: 'INFO', module: 'visibility_access', format: 'json' });
    expect(mockedRequest).toHaveBeenCalledWith(
      'POST',
      '/logs/export',
      { format: 'json' },
      expect.objectContaining({
        params: { level: 'INFO', module: 'visibility_access' },
        responseType: 'blob',
      }),
    );
  });

  it('导出选中范围：逗号串 logIds 映射为后端 log_ids int 数组', async () => {
    mockedRequest.mockResolvedValue('json-bytes');
    await logsApi.export({ logIds: '5203,5202', format: 'excel' });
    expect(mockedRequest).toHaveBeenCalledWith(
      'POST',
      '/logs/export',
      { log_ids: [5203, 5202], format: 'excel' },
      expect.objectContaining({ responseType: 'blob' }),
    );
  });

  it('空筛选不发送冗余 query/body 字段（无 level/module/logIds 时）', async () => {
    mockedRequest.mockResolvedValue('json-bytes');
    await logsApi.export();
    expect(mockedRequest).toHaveBeenCalledWith(
      'POST',
      '/logs/export',
      {},
      expect.objectContaining({ params: {}, responseType: 'blob' }),
    );
  });

  it('blob 响应原样透传（后端 FileResponse 文件流）', async () => {
    const blob = new Blob(['{"ID":5203}'], { type: 'application/json' });
    mockedRequest.mockResolvedValue(blob);
    const result = await logsApi.export({ format: 'json' });
    expect(result).toBe(blob);
  });
});

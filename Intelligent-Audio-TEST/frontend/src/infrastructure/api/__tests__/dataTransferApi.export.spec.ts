/**
 * dataTransferApi.export 契约测试（INT-631 数据迁移前端适配）
 * 后端 TaskDataExportRequest 为平铺 snake_case（task_ids / include_ref_params / include_audios），
 * 前端不得再发嵌套 options——否则网关 extra=ignore 静默丢弃，勾选项失效（回归锁定）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}));

import { request } from '../../http/client';
import { dataTransferApi } from '../dataTransferApi';

const mockedRequest = vi.mocked(request);

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('dataTransferApi.exportTasks 平铺契约', () => {
  it('请求体平铺 snake_case，不嵌套 options（网关契约 TaskDataExportRequest）', async () => {
    mockedRequest.mockResolvedValue(new Blob(['zip']));

    await dataTransferApi.exportTasks([11, 12], {
      includeRefParams: true,
      includeAudios: false,
    });

    expect(mockedRequest).toHaveBeenCalledWith(
      'POST',
      '/data-transfer/export',
      {
        task_ids: [11, 12],
        include_ref_params: true,
        include_audios: false,
      },
      expect.objectContaining({ responseType: 'blob' }),
    );
  });

  it('camelCase Domain 选项映射为 snake_case 字段', async () => {
    mockedRequest.mockResolvedValue(new Blob(['zip']));

    await dataTransferApi.exportTasks(['a', 'b'], {
      includeRefParams: false,
      includeAudios: true,
    });

    expect(mockedRequest).toHaveBeenCalledWith(
      'POST',
      '/data-transfer/export',
      {
        task_ids: ['a', 'b'],
        include_ref_params: false,
        include_audios: true,
      },
      expect.objectContaining({ responseType: 'blob' }),
    );
  });
});

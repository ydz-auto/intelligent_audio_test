/**
 * INT-630：apisApi / apiConfigAdapter 契约测试
 * 锁定 snake_case ↔ camelCase 转换与端点路径不被回退；
 * getAll 查询参数 camelCase Domain → snake_case query（对齐
 * api_gateway/schemas/api.py::ApiListQuery：page / per_page / keyword / status / algorithm_type）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}));

import { request } from '../../http/client';
import { apisApi } from '../apisApi';
import { toAPIConfig } from '../../adapters/apiConfigAdapter';
import type { APIConfigDto } from '../../dto/apiConfigDto';

const mockedRequest = vi.mocked(request);

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('INT-630：toAPIConfig snake→camel 映射', () => {
  it('全字段映射（含 endpoints / rms_spl_mapping_id）', () => {
    const domain = toAPIConfig({
      id: 1,
      name: '火山 Realtime',
      vendor: 'volc_ast',
      api_url: 'https://example.com/v1',
      status: 'online',
      algorithm_type: 'voice_llm',
      default_max_process: 4,
      endpoints: [{ endpoint: '/v1/audio', max_process: 4 }],
      rms_spl_mapping_id: 12,
      created_at: '2026-10-17T00:00:00Z',
    } as unknown as APIConfigDto);

    expect(domain.id).toBe(1);
    expect(domain.name).toBe('火山 Realtime');
    expect(domain.apiUrl).toBe('https://example.com/v1');
    expect(domain.algorithmType).toBe('voice_llm');
    expect(domain.defaultMaxProcess).toBe(4);
    expect(domain.rmsSplMappingId).toBe(12);
    expect(domain.endpoints?.[0].endpoint).toBe('/v1/audio');
    expect(domain.endpoints?.[0].maxProcess).toBe(4);
  });
});

describe('INT-630：apisApi 端点与查询参数契约', () => {
  it('getAll 走 GET /apis 且查询参数转 snake_case（page/per_page/keyword/status/algorithm_type）', async () => {
    mockedRequest.mockResolvedValueOnce({
      items: [{ id: 1, name: 'A' }],
      total: 1,
      page: 1,
      per_page: 20,
      pages: 1,
    });
    const result = await apisApi.getAll({
      page: 1,
      perPage: 20,
      keyword: '火山',
      status: 'online',
      algorithmType: 'voice_llm',
    });
    expect(mockedRequest).toHaveBeenCalledWith('GET', '/apis', null, {
      params: { page: 1, per_page: 20, keyword: '火山', status: 'online', algorithm_type: 'voice_llm' },
    });
    // 分页响应展平为 Domain 数组（camelCase）
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe(1);
    expect(result[0].name).toBe('A');
  });

  it('getAll 空参不带 query 参数', async () => {
    mockedRequest.mockResolvedValueOnce({ items: [], total: 0 });
    await apisApi.getAll();
    expect(mockedRequest).toHaveBeenCalledWith('GET', '/apis', null, { params: {} });
  });

  it('create 请求体转 snake_case（对齐 ApiCreateInput）', async () => {
    mockedRequest.mockResolvedValueOnce({ id: 9 });
    await apisApi.create({ name: '新API', apiUrl: 'https://example.com', rmsSplMappingId: 3 });
    expect(mockedRequest).toHaveBeenCalledWith(
      'POST',
      '/apis',
      {
        name: '新API',
        vendor: undefined,
        api_url: 'https://example.com',
        description: undefined,
        status: undefined,
        meta: undefined,
        algorithm_type: undefined,
        default_max_process: undefined,
        default_max_timeout: undefined,
        default_max_audio_duration: undefined,
        endpoints: undefined,
        output_types: undefined,
        device_type: undefined,
        adapter_class: undefined,
        audio_config: undefined,
        rms_spl_mapping_id: 3,
      },
      {}
    );
  });

  it('healthCheck 走 POST /apis/{id}/health 并映射 ApiHealthCheckResult', async () => {
    mockedRequest.mockResolvedValueOnce({
      id: 5,
      status: 'ok',
      health_score: 98,
      api_url_status: 'ok',
      endpoints_status: 'ok',
      status_code: 200,
      response_time: '12.30ms',
    });
    const result = await apisApi.healthCheck(5);
    expect(mockedRequest).toHaveBeenCalledWith('POST', '/apis/5/health', null, {});
    expect(result.status).toBe('ok');
    expect(result.healthScore).toBe(98);
    expect(result.apiUrlStatus).toBe('ok');
    expect(result.responseTime).toBe('12.30ms');
  });

  it('delete 走 DELETE /apis/{id}', async () => {
    mockedRequest.mockResolvedValueOnce(null);
    await apisApi.delete(9);
    expect(mockedRequest).toHaveBeenCalledWith('DELETE', '/apis/9');
  });
});

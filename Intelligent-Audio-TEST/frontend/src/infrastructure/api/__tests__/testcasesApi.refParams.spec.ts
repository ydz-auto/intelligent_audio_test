/**
 * testcasesApi ref-params 读写契约测试（INT-65）
 * 覆盖：GET/PUT 封装的 URL、请求体契约（camelCase referenceParams）、
 * 响应 snake_case/camelCase 双兼容映射。
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

describe('testcasesApi ref-params 契约', () => {
  it('getRefParams 走 GET /testcases/{id}/rounds/{n}/ref-params 并映射 camelCase', async () => {
    mockedRequest.mockResolvedValueOnce({
      roundNumber: 2,
      referenceParamsPath: '/storage/refs/case-1-round2.json',
      referenceParams: { volume: 60 },
    });
    const data = await testcasesApi.getRefParams('case-1', 2);
    expect(mockedRequest).toHaveBeenCalledWith('GET', '/testcases/case-1/rounds/2/ref-params');
    expect(data.roundNumber).toBe(2);
    expect(data.referenceParamsPath).toBe('/storage/refs/case-1-round2.json');
    expect(data.referenceParams).toEqual({ volume: 60 });
  });

  it('getRefParams 兼容 snake_case 响应', async () => {
    mockedRequest.mockResolvedValueOnce({
      round_number: 1,
      reference_params_path: '/refs/p1.json',
      reference_params: { gain: 3 },
    });
    const data = await testcasesApi.getRefParams(9, 1);
    expect(data.roundNumber).toBe(1);
    expect(data.referenceParamsPath).toBe('/refs/p1.json');
    expect(data.referenceParams).toEqual({ gain: 3 });
  });

  it('updateRefParams 以 camelCase referenceParams 请求体 PUT', async () => {
    mockedRequest.mockResolvedValueOnce({
      round_number: 3,
      reference_params_path: '/refs/p3.json',
      reference_params: { a: 1 },
    });
    const data = await testcasesApi.updateRefParams('case-2', 3, { a: 1 });
    expect(mockedRequest).toHaveBeenCalledWith(
      'PUT',
      '/testcases/case-2/rounds/3/ref-params',
      { referenceParams: { a: 1 } },
    );
    expect(data.roundNumber).toBe(3);
    expect(data.referenceParams).toEqual({ a: 1 });
  });
});

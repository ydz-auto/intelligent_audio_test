/**
 * INT-300：apiRmsSplApi / apiRmsSplAdapter 契约测试
 * 锁定 snake_case ↔ camelCase 转换与端点路径不被回退；
 * 校准请求体 {calibration_data:{points}} 与 set-default {mapping_id} 形状对齐
 * api_gateway/schemas/api_rms_spl.py。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}));

import { request } from '../../http/client';
import { apiRmsSplApi } from '../apiRmsSplApi';
import { toApiRmsSplMapping } from '../../adapters/apiRmsSplAdapter';
import type { ApiRmsSplMappingItemDto } from '../../dto/apiRmsSplDto';

const mockedRequest = vi.mocked(request);

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('INT-300：toApiRmsSplMapping snake→camel 映射', () => {
  it('全字段映射（含校准点内层 target_spl/gain_linear/rms_dbfs）', () => {
    const domain = toApiRmsSplMapping({
      id: 5,
      api_id: 12,
      name: '火山 Realtime 基线',
      vendor: 'volc_ast',
      protocol: 'websocket',
      reference_spl: 65,
      reference_gain_linear: 1.0,
      calibration_status: 'calibrated',
      calibration_points: [
        { target_spl: 45, gain_linear: 0.1, rms_dbfs: -30.2 },
        { target_spl: 65, gain_linear: 1.0, rms_dbfs: -29.8 },
      ],
      min_gain_linear: 0.001,
      max_gain_linear: 10.0,
      is_calibrated: true,
    } as ApiRmsSplMappingItemDto);

    expect(domain.id).toBe(5);
    expect(domain.apiId).toBe(12);
    expect(domain.name).toBe('火山 Realtime 基线');
    expect(domain.vendor).toBe('volc_ast');
    expect(domain.protocol).toBe('websocket');
    expect(domain.referenceSpl).toBe(65);
    expect(domain.referenceGainLinear).toBe(1.0);
    expect(domain.calibrationStatus).toBe('calibrated');
    expect(domain.isCalibrated).toBe(true);
    expect(domain.minGainLinear).toBe(0.001);
    expect(domain.maxGainLinear).toBe(10.0);
    expect(domain.calibrationPoints).toEqual([
      { targetSpl: 45, gainLinear: 0.1, rmsDbfs: -30.2 },
      { targetSpl: 65, gainLinear: 1.0, rmsDbfs: -29.8 },
    ]);
  });

  it('NULL 容忍：可选字段缺省 → undefined，calibration_points null → 空数组', () => {
    const domain = toApiRmsSplMapping({
      id: 7,
      api_id: 3,
    } as unknown as ApiRmsSplMappingItemDto);
    expect(domain.name).toBeUndefined();
    expect(domain.vendor).toBeUndefined();
    expect(domain.referenceSpl).toBeUndefined();
    expect(domain.calibrationStatus).toBeUndefined();
    expect(domain.calibrationPoints).toEqual([]);
    expect(domain.isCalibrated).toBeUndefined();
  });
});

describe('INT-300：apiRmsSplApi 端点与请求体契约', () => {
  it('getAll 走 GET /digital-spl 且 query 转 snake_case（page/per_page/api_id/calibration_status）', async () => {
    mockedRequest.mockResolvedValueOnce({
      items: [{ id: 1, api_id: 2 }],
      total: 1,
      page: 1,
      per_page: 10,
      pages: 1,
    });
    await apiRmsSplApi.getAll({ page: 2, perPage: 20, apiId: 9, calibrationStatus: 'calibrated' });
    expect(mockedRequest).toHaveBeenCalledWith('GET', '/digital-spl', null, {
      params: { page: 2, per_page: 20, api_id: 9, calibration_status: 'calibrated' },
    });
  });

  it('getByApi 走 GET /digital-spl/by-api/{id} 并映射 items/total', async () => {
    mockedRequest.mockResolvedValueOnce({
      items: [{ id: 4, api_id: 9, name: '默认' }],
      total: 1,
    });
    const result = await apiRmsSplApi.getByApi(9);
    expect(mockedRequest).toHaveBeenCalledWith('GET', '/digital-spl/by-api/9', null, {});
    expect(result.total).toBe(1);
    expect(result.items[0].apiId).toBe(9);
    expect(result.items[0].name).toBe('默认');
  });

  it('create 请求体转 snake_case（api_id + calibration_data.points）', async () => {
    mockedRequest.mockResolvedValueOnce({ id: 11 });
    await apiRmsSplApi.create({
      apiId: 12,
      name: '基线',
      referenceSpl: 65,
      referenceGainLinear: 1.0,
      calibrationPoints: [{ targetSpl: 65, gainLinear: 1.0, rmsDbfs: -30 }],
      minGainLinear: 0.001,
      maxGainLinear: 10,
    });
    expect(mockedRequest).toHaveBeenCalledWith('POST', '/digital-spl', {
      api_id: 12,
      name: '基线',
      description: undefined,
      vendor: undefined,
      protocol: undefined,
      reference_spl: 65,
      reference_gain_linear: 1.0,
      calibration_status: undefined,
      calibration_data: { points: [{ target_spl: 65, gain_linear: 1.0, rms_dbfs: -30 }] },
      min_gain_linear: 0.001,
      max_gain_linear: 10,
    }, {});
  });

  it('update 不携带 api_id（更新语义，归属不可变）', async () => {
    mockedRequest.mockResolvedValueOnce({ id: 11 });
    await apiRmsSplApi.update(11, { name: '改名', protocol: 'http' });
    expect(mockedRequest).toHaveBeenCalledWith('PUT', '/digital-spl/11', {
      name: '改名',
      description: undefined,
      vendor: undefined,
      protocol: 'http',
      reference_spl: undefined,
      reference_gain_linear: undefined,
      calibration_status: undefined,
      calibration_data: undefined,
      min_gain_linear: undefined,
      max_gain_linear: undefined,
    }, {});
  });

  it('calibrate 请求体为 {calibration_data:{points:[...]}}（对齐 RmsSplCalibrateRequest）', async () => {
    mockedRequest.mockResolvedValueOnce({ id: 11 });
    await apiRmsSplApi.calibrate(11, [
      { targetSpl: 45, gainLinear: 0.1 },
      { targetSpl: 65, gainLinear: 1.0, rmsDbfs: -30.5 },
    ]);
    expect(mockedRequest).toHaveBeenCalledWith('POST', '/digital-spl/11/calibrate', {
      calibration_data: {
        points: [
          { target_spl: 45, gain_linear: 0.1, rms_dbfs: null },
          { target_spl: 65, gain_linear: 1.0, rms_dbfs: -30.5 },
        ],
      },
    }, {});
  });

  it('setDefault：mappingId 数字化；null 表示清除默认', async () => {
    mockedRequest.mockResolvedValueOnce({ api_id: 9, rms_spl_mapping_id: 4 });
    await apiRmsSplApi.setDefault(9, 4);
    expect(mockedRequest).toHaveBeenCalledWith('POST', '/digital-spl/by-api/9/set-default', { mapping_id: 4 }, {});

    mockedRequest.mockResolvedValueOnce({ api_id: 9, rms_spl_mapping_id: null });
    await apiRmsSplApi.setDefault(9, null);
    expect(mockedRequest).toHaveBeenCalledWith('POST', '/digital-spl/by-api/9/set-default', { mapping_id: null }, {});
  });

  it('remove 走 DELETE /digital-spl/{id}', async () => {
    mockedRequest.mockResolvedValueOnce(null);
    await apiRmsSplApi.remove(11);
    expect(mockedRequest).toHaveBeenCalledWith('DELETE', '/digital-spl/11', null, {});
  });
});

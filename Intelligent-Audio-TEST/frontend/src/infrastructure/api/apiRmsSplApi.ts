/**
 * Digital SPL (API RMS→SPL 映射，数字域灵敏度) API module
 * 出口契约：Domain（camelCase）；DTO 转换全部收敛在 adapters。
 * 区别于 splApi.ts（设备物理域 /spl）。
 */
import { request, type RequestOptions } from '../http/client';
import { toPaginated } from '../adapters/commonAdapter';
import {
  toApiRmsSplMapping,
  toApiRmsSplCreateDto,
  toApiRmsSplUpdateDto,
  toApiRmsSplQueryDto,
  toApiRmsSplCalibrateDto,
  toApiRmsSplSetDefaultDto,
} from '../adapters/apiRmsSplAdapter';
import type {
  ApiRmsSplMappingItemDto,
  ApiRmsSplMappingListDto,
  ApiRmsSplByApiDto,
} from '../dto/apiRmsSplDto';
import type {
  ApiRmsSplMapping,
  ApiRmsSplMappingList,
  ApiRmsSplQuery,
  ApiRmsSplUpsertInput,
  ApiCalibrationPoint,
} from '../../domain/model/apiRmsSpl';

export const apiRmsSplApi = {
  /** 映射分页列表 → Paginated<ApiRmsSplMapping>（camelCase） */
  async getAll(params: ApiRmsSplQuery = {}, options: RequestOptions = {}): Promise<ApiRmsSplMappingList> {
    const dto = await request<ApiRmsSplMappingListDto>('GET', '/digital-spl', null, {
      ...options,
      params: toApiRmsSplQueryDto(params),
    });
    return toPaginated(dto, toApiRmsSplMapping);
  },

  async getOne(id: string | number, options: RequestOptions = {}): Promise<ApiRmsSplMapping> {
    const dto = await request<ApiRmsSplMappingItemDto>('GET', `/digital-spl/${id}`, null, options);
    return toApiRmsSplMapping(dto);
  },

  /** 按 API 的映射列表（非分页结构：items + total） */
  async getByApi(apiId: string | number, options: RequestOptions = {}): Promise<{ items: ApiRmsSplMapping[]; total: number }> {
    const dto = await request<ApiRmsSplByApiDto>('GET', `/digital-spl/by-api/${apiId}`, null, options);
    return {
      items: (dto.items || []).map(toApiRmsSplMapping),
      total: dto.total ?? 0,
    };
  },

  /** 创建映射：camelCase → snake_case 请求体（返回 IdData） */
  async create(input: ApiRmsSplUpsertInput, options: RequestOptions = {}) {
    return request('POST', '/digital-spl', toApiRmsSplCreateDto(input), options);
  },

  async update(id: string | number, input: ApiRmsSplUpsertInput, options: RequestOptions = {}) {
    return request('PUT', `/digital-spl/${id}`, toApiRmsSplUpdateDto(input), options);
  },

  async remove(id: string | number, options: RequestOptions = {}) {
    return request('DELETE', `/digital-spl/${id}`, null, options);
  },

  /** 执行校准（后端分布式锁互斥，冲突返回 409） */
  async calibrate(id: string | number, calibrationPoints: ApiCalibrationPoint[], options: RequestOptions = {}) {
    return request(
      'POST',
      `/digital-spl/${id}/calibrate`,
      toApiRmsSplCalibrateDto(calibrationPoints),
      options,
    );
  },

  /** 设为 API 当前默认映射；mappingId 为空表示清除默认 */
  async setDefault(apiId: string | number, mappingId: string | number | null, options: RequestOptions = {}) {
    return request(
      'POST',
      `/digital-spl/by-api/${apiId}/set-default`,
      toApiRmsSplSetDefaultDto(mappingId),
      options,
    );
  },
};

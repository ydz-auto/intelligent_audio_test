/**
 * APIs (external API services) API module
 * 出口契约：Domain（camelCase）
 */
import { request, type RequestOptions } from '../http/client';
import { toAPIConfig, toApiUpsertDto, toApiHealthCheckResult } from '../adapters/apiConfigAdapter';
import { toArrayOrPaginated } from '../adapters/commonAdapter';
import type { APIConfigDto, PaginatedDto, ApiHealthCheckDto } from '../dto';
import type { APIConfig, ApiHealthCheckResult } from '../../domain/model/apiConfig';

export const apisApi = {
  /** API 列表（兼容分页对象/数组/裸 data 三种响应）→ APIConfig[] */
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}): Promise<APIConfig[]> {
    const raw = await request<PaginatedDto<APIConfigDto> | APIConfigDto[]>('GET', '/apis', null, { ...options, params });
    return toArrayOrPaginated(raw, toAPIConfig);
  },

  async getOne(id: string | number): Promise<APIConfig> {
    const dto = await request<APIConfigDto>('GET', `/apis/${id}`);
    return toAPIConfig(dto);
  },

  /** 创建/更新：Domain(camelCase) → snake_case 请求体 */
  async create(apiData: Partial<APIConfig>, options: RequestOptions = {}) {
    return request('POST', '/apis', toApiUpsertDto(apiData), options);
  },

  async update(id: string | number, apiData: Partial<APIConfig>, options: RequestOptions = {}) {
    return request('PUT', `/apis/${id}`, toApiUpsertDto(apiData), options);
  },

  async delete(id: string | number) {
    return request('DELETE', `/apis/${id}`);
  },

  /** 连接测试（POST /apis/{id}/health，后端 health_check 与 test_connection 同实现）→ ApiHealthCheckResult（camelCase） */
  async healthCheck(id: string | number, options: RequestOptions = {}): Promise<ApiHealthCheckResult> {
    const dto = await request<ApiHealthCheckDto>('POST', `/apis/${id}/health`, null, options);
    return toApiHealthCheckResult(dto);
  },

  async testConnection(id: string | number, options: RequestOptions = {}): Promise<ApiHealthCheckResult> {
    return this.healthCheck(id, options);
  },

  async stopTest(id: string | number, options: RequestOptions = {}) {
    return request('POST', `/apis/${id}/stop-test`, null, options);
  }
};

/**
 * Laboratories API module
 *
 * 出口契约：camelCase Domain（domain/model/laboratory.ts）。
 * 请求体/查询参数：显式 snake_case（page/per_page/keyword/status，APIModel 双兼容）。
 * 后端：api_gateway/routes/laboratory_bp.py，前缀 /api/v1/laboratories（INT-655）。
 */
import { request, type RequestOptions } from '../http/client';
import type { LaboratoryItemDto, LaboratoryListDto } from '../dto/laboratoryDto';
import type { Laboratory } from '../../domain/model/laboratory';
import type { Paginated } from '../../domain/model/common';
import { toLaboratoryPage, toLaboratoryList } from '../adapters/laboratoryAdapter';

/** 实验室列表查询参数（snake_case 发往后端） */
export interface LaboratoryListQueryParams {
  page?: number
  per_page?: number
  keyword?: string
  status?: string
}

export const laboratoriesApi = {
  /** 实验室分页列表（PaginatedData[LaboratoryItem] → Paginated<Laboratory>） */
  async getAll(params: LaboratoryListQueryParams = {}, options: RequestOptions = {}): Promise<Paginated<Laboratory>> {
    const dto = await request<LaboratoryListDto>('GET', '/laboratories', null, { ...options, params });
    return toLaboratoryPage(dto);
  },

  /** 实验室数组兜底（供「实验室」facet 选项等取全部场景） */
  async getAllFlat(params: LaboratoryListQueryParams = {}, options: RequestOptions = {}): Promise<Laboratory[]> {
    const dto = await request<LaboratoryListDto | LaboratoryItemDto[]>('GET', '/laboratories', null, { ...options, params });
    return toLaboratoryList(dto as LaboratoryListDto);
  },

  /** 实验室详情 */
  async getOne(id: number, options: RequestOptions = {}): Promise<Laboratory> {
    const dto = await request<LaboratoryItemDto>('GET', `/laboratories/${id}`, null, options);
    return toLaboratoryList({ items: [dto], total: 1, page: 1, per_page: 1, pages: 1 } as LaboratoryListDto)[0];
  },

  /** 实验室资源统计（GET /{id}/summary） */
  async getSummary(id: number, options: RequestOptions = {}): Promise<{ deviceCount?: number; playbackDeviceCount?: number; testCaseCount?: number }> {
    const dto = await request<{ device_count?: number; playback_device_count?: number; test_case_count?: number }>('GET', `/laboratories/${id}/summary`, null, options);
    return {
      deviceCount: dto?.device_count,
      playbackDeviceCount: dto?.playback_device_count,
      testCaseCount: dto?.test_case_count,
    };
  },

  /** 创建实验室 */
  async create(data: Partial<Laboratory>, options: RequestOptions = {}) {
    return request('POST', '/laboratories', toLaboratoryUpsertDto(data), options);
  },

  /** 更新实验室 */
  async update(id: number, data: Partial<Laboratory>, options: RequestOptions = {}) {
    return request('PUT', `/laboratories/${id}`, toLaboratoryUpsertDto(data), options);
  },

  /** 删除实验室 */
  async delete(id: number, options: RequestOptions = {}) {
    return request<void>('DELETE', `/laboratories/${id}`, null, options);
  },
};

/** camelCase Domain Laboratory → snake_case 请求体（创建/更新共用） */
function toLaboratoryUpsertDto(data: Partial<Laboratory>): Record<string, unknown> {
  const dto: Record<string, unknown> = {}
  if (data.code !== undefined) dto.code = data.code
  if (data.name !== undefined) dto.name = data.name
  if (data.building !== undefined) dto.building = data.building
  if (data.floor !== undefined) dto.floor = data.floor
  if (data.roomNumber !== undefined) dto.room_number = data.roomNumber
  if (data.description !== undefined) dto.description = data.description
  if (data.status !== undefined) dto.status = data.status
  return dto
}

/**
 * 数字域 RMS-SPL 映射真实 API（infrastructure/api 层；16_设备域.md §10 组件树落位，接线卡 INT-649）。
 * 经基座 client.ts 统一 fetch（INT-605）：baseURL /api/v1、JWT 注入、错误码归一。
 * 契约对照 api_gateway/routes/digital_spl_bp.py + schemas/api_rms_spl.py + api_bp.py 实测：
 *   GET    /digital-spl                      列表（api_id/calibration_status 服务端过滤，per_page 钳制 [1,100]）
 *   GET    /digital-spl/{id}                 详情
 *   POST   /digital-spl                      新增映射（RmsSplMappingCreateRequest → IdData）
 *   PUT    /digital-spl/{id}                 编辑映射（RmsSplMappingUpdateRequest）
 *   DELETE /digital-spl/{id}                 删除映射
 *   POST   /digital-spl/{id}/calibrate       数字校准（RmsSplCalibrateRequest 点集全量替换，409 分布式锁互斥）
 *   POST   /digital-spl/by-api/{apiId}/set-default  RmsSplSetDefaultRequest（mapping_id 空清除）
 *   GET    /apis                             关联 API facet 选项（分页信封，含 rms_spl_mapping_id 默认指针）
 * 读侧字段名 calibration_points（平铺点集）；写侧请求体用 calibration_data.points（全量替换）。
 */
import { request, type ApiRequestOptions } from '@/infrastructure/api/client'
import type {
  ApiConfigRef,
  ApiRmsSplMapping,
} from '@/domain/models/digitalSpl'
import type {
  ApiConfigRefDto,
  ApiRmsSplMappingListDto,
} from '@/infrastructure/dto/digital-spl.dto'
import {
  apiConfigRefFromDto,
  apiRmsSplMappingFromDto,
  digitalSplCalibrateRequestFromDomain,
  digitalSplCreateRequestFromDomain,
  digitalSplSetDefaultRequestFromDomain,
  digitalSplUpdateRequestFromDomain,
} from '@/infrastructure/adapters/digitalSplAdapter'

/** 数字域列表分页上限（后端 RmsSplQueryService per_page 钳制 [1,100]） */
const DIGITAL_SPL_PAGE_SIZE = 100
/** 关联 API facet 全量取回分页上限 */
const API_REFS_PAGE_SIZE = 100

/** 列表（§4.3；GET /digital-spl → 分页信封，取 items 映射为 ApiRmsSplMapping[]） */
export async function fetchDigitalSplMappings(
  options: ApiRequestOptions = {}
): Promise<ApiRmsSplMapping[]> {
  const dto = await request<ApiRmsSplMappingListDto>(
    'GET',
    '/digital-spl',
    undefined,
    { ...options, params: { page: 1, per_page: DIGITAL_SPL_PAGE_SIZE } }
  )
  return (dto?.items ?? []).map(apiRmsSplMappingFromDto)
}

/** 被测 API facet 选项（§4.1.1；GET /apis → items 映射，含 rmsSplMappingId 默认指针） */
export async function fetchApiRefs(
  options: ApiRequestOptions = {}
): Promise<ApiConfigRef[]> {
  const dto = await request<{ items: ApiConfigRefDto[]; total: number }>(
    'GET',
    '/apis',
    undefined,
    { ...options, params: { page: 1, per_page: API_REFS_PAGE_SIZE } }
  )
  return (dto?.items ?? []).map(apiConfigRefFromDto)
}

/** 新增映射（§6.12；POST /digital-spl；返回 IdData） */
export async function createDigitalSplMapping(
  input: Omit<ApiRmsSplMapping, 'id' | 'createdAt' | 'updatedAt'>,
  options: ApiRequestOptions = {}
): Promise<{ id: number }> {
  const body = digitalSplCreateRequestFromDomain(input)
  const dto = await request<{ id: number }>('POST', '/digital-spl', body, options)
  return { id: dto?.id ?? 0 }
}

/** 编辑映射（§6.12；PUT /digital-spl/{id}） */
export async function updateDigitalSplMapping(
  id: number,
  patch: Partial<ApiRmsSplMapping>,
  options: ApiRequestOptions = {}
): Promise<void> {
  const body = digitalSplUpdateRequestFromDomain(patch)
  await request('PUT', `/digital-spl/${id}`, body, options)
}

/** 删除映射（§4.3.1；DELETE /digital-spl/{id}；成功返回 success=true，失败由 ApiError 承载） */
export async function deleteDigitalSplMapping(
  id: number,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; message?: string }> {
  await request('DELETE', `/digital-spl/${id}`, undefined, options)
  return { success: true }
}

/** 数字校准（§6.10；POST /digital-spl/{id}/calibrate；点集全量替换并置已校准，冲突 409） */
export async function calibrateDigitalSplMapping(
  id: number,
  points: Array<{ targetSpl: number; gainLinear: number; rmsDbfs: number | null }>,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; message?: string }> {
  const body = digitalSplCalibrateRequestFromDomain(points)
  await request('POST', `/digital-spl/${id}/calibrate`, body, options)
  return { success: true }
}

/** 设默认/清除默认（§4.3.1；POST /digital-spl/by-api/{apiId}/set-default，mapping_id 空清除） */
export async function setDefaultDigitalSplMapping(
  apiId: number,
  mappingId: number | null,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean }> {
  const body = digitalSplSetDefaultRequestFromDomain(mappingId)
  await request('POST', `/digital-spl/by-api/${apiId}/set-default`, body, options)
  return { success: true }
}

/** 供测试/组件读取用的类型重导出（domain 模型口径一致） */
export type { ApiConfigRef, ApiRmsSplMapping }

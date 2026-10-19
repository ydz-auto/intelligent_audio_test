/**
 * 物理域 SPL 映射真实 API（infrastructure/api 层；16_设备域.md §10 组件树落位，接线卡 INT-649）。
 * 经基座 client.ts 统一 fetch（INT-605）：baseURL /api/v1、JWT 注入、错误码归一。
 * 契约对照 api_gateway/routes/spl_bp.py + schemas/spl.py 实测：
 *   GET    /spl                            列表（keyword/calibration_status/device_id/page/per_page）
 *   GET    /spl/stats                       统计（SplStatsData）
 *   GET    /spl/{id}                        详情
 *   GET    /spl/{id}/history                校准历史（SplHistoryData items+total）
 *   POST   /spl                             新增映射（SPLMappingCreateRequest → IdData）
 *   PUT    /spl/{id}                        编辑映射（SPLMappingUpdateRequest；距离/频率变更重置校准在 feature 内处理）
 *   DELETE /spl/{id}                        删除映射
 *   POST   /spl/{id}/calibrate              执行校准（现状后端为模拟校准 §11-12，请求体忽略，返回 SplCalibrationResult）
 *   GET    /playback-devices                关联播放设备 facet 选项（分页信封，取 items 子集）
 * 列表接口返回分页信封；页面为前端过滤分页（§4.2「接线后 URL 态化」前保持全量取回）。
 */
import { request, type ApiRequestOptions } from '@/infrastructure/api/client'
import type {
  PlaybackDeviceRef,
  SplHistoryItem,
  SplMapping,
  SplStats,
} from '@/domain/models/splMapping'
import type {
  SplCalibrationResultDto,
  SplHistoryDto,
  SplMappingListDto,
  SplStatsDto,
} from '@/infrastructure/dto/spl.dto'
import type { PlaybackDeviceItemDto } from '@/infrastructure/dto/playback-device.dto'
import {
  playbackDeviceRefFromPlaybackDto,
  splCalibrationResultFromDto,
  splHistoryItemFromDto,
  splMappingCreateRequestFromDomain,
  splMappingFromDto,
  splMappingUpdateRequestFromDomain,
  splStatsFromDto,
} from '@/infrastructure/adapters/splAdapter'

/** 物理域全量取回分页上限（后端无钳制；页面前端过滤分页） */
const SPL_LIST_PAGE_SIZE = 1000
/** 播放设备 facet 全量取回分页上限 */
const PLAYBACK_DEVICE_PAGE_SIZE = 1000

/** 列表（§4.2；GET /spl → SplMappingListDto，取 items 映射为 SplMapping[]） */
export async function fetchSplMappings(
  options: ApiRequestOptions = {}
): Promise<SplMapping[]> {
  const dto = await request<SplMappingListDto>('GET', '/spl', undefined, {
    ...options,
    params: { page: 1, per_page: SPL_LIST_PAGE_SIZE },
  })
  return (dto?.items ?? []).map(splMappingFromDto)
}

/** 某播放设备的声压映射（§6.4 关联弹窗选项来源；GET /spl/by-device/{device_id}，V9.7.10 loadSplMappings 同源） */
export async function fetchSplMappingsByDevice(
  deviceId: number,
  options: ApiRequestOptions = {}
): Promise<SplMapping[]> {
  const dto = await request<SplMappingListDto>('GET', `/spl/by-device/${deviceId}`, undefined, {
    ...options,
    params: { page: 1, per_page: SPL_LIST_PAGE_SIZE },
  })
  return (dto?.items ?? []).map(splMappingFromDto)
}

/** 统计（§4.1.2；GET /spl/stats → SplStatsData） */
export async function fetchSplStats(
  options: ApiRequestOptions = {}
): Promise<SplStats> {
  const dto = await request<SplStatsDto>('GET', '/spl/stats', undefined, options)
  return splStatsFromDto(dto)
}

/** 关联播放设备 facet 选项（§4.1.1；GET /playback-devices → items 映射为 PlaybackDeviceRef[]） */
export async function fetchPlaybackDeviceRefs(
  options: ApiRequestOptions = {}
): Promise<PlaybackDeviceRef[]> {
  const dto = await request<{ items: PlaybackDeviceItemDto[]; total: number }>(
    'GET',
    '/playback-devices',
    undefined,
    { ...options, params: { page: 1, per_page: PLAYBACK_DEVICE_PAGE_SIZE } }
  )
  return (dto?.items ?? []).map(playbackDeviceRefFromPlaybackDto)
}

/** 校准历史（§6.9；GET /spl/{id}/history → SplHistoryData，取 items 映射） */
export async function fetchSplHistory(
  id: number,
  options: ApiRequestOptions = {}
): Promise<SplHistoryItem[]> {
  const dto = await request<SplHistoryDto>(
    'GET',
    `/spl/${id}/history`,
    undefined,
    options
  )
  return (dto?.items ?? []).map(splHistoryItemFromDto)
}

/** 新增映射（§6.7；POST /spl；deviceName/deviceModel 由后端按 device_id 关联派生，返回 IdData） */
export async function createSplMapping(
  input: Omit<
    SplMapping,
    'id' | 'createdAt' | 'updatedAt' | 'deviceName' | 'deviceModel'
  >,
  options: ApiRequestOptions = {}
): Promise<{ id: number }> {
  const body = splMappingCreateRequestFromDomain(input)
  const dto = await request<{ id: number }>('POST', '/spl', body, options)
  return { id: dto?.id ?? 0 }
}

/** 编辑映射（§6.7；PUT /spl/{id}；距离/频率变更重置为未校准在 feature 内处理） */
export async function updateSplMapping(
  id: number,
  patch: Partial<SplMapping>,
  options: ApiRequestOptions = {}
): Promise<void> {
  const body = splMappingUpdateRequestFromDomain(patch)
  await request('PUT', `/spl/${id}`, body, options)
}

/** 删除映射（§4.2.1；DELETE /spl/{id}；成功返回 success=true，失败由 ApiError 承载） */
export async function deleteSplMapping(
  id: number,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; message?: string }> {
  await request('DELETE', `/spl/${id}`, undefined, options)
  return { success: true }
}

/** 执行校准（§4.2.1；POST /spl/{id}/calibrate；现状后端为模拟校准 §11-12，请求体忽略） */
export async function calibrateSplMapping(
  id: number,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; calibrationStatus: string; message?: string }> {
  const dto = await request<SplCalibrationResultDto>(
    'POST',
    `/spl/${id}/calibrate`,
    undefined,
    options
  )
  return splCalibrationResultFromDto(dto)
}

/** 供测试/组件读取用的类型重导出（domain 模型口径一致） */
export type { PlaybackDeviceRef, SplHistoryItem, SplMapping, SplStats }

/**
 * SPL Adapter —— SplDto(snake_case) → SPL Domain(camelCase)
 *
 * 出口契约：domain/model/spl.ts；查询参数/请求体转换在同文件下半部分。
 */
import type {
  SPLMapping,
  SPLStats,
  SPLHistoryItem,
  SPLHistoryList,
  SPLByDeviceItem,
  SPLByDeviceList,
  SPLQuery,
  SPLPlayToneInput,
  CalibrationData,
} from '../../domain/model/spl'
import type {
  SplMappingItemDto,
  SplMappingListDto,
  SplHistoryItemDto,
  SplHistoryDto,
  SplStatsDto,
  SplByDeviceItemDto,
  SplByDeviceDto,
  SplQueryDto,
  SplCreateDto,
  SplUpdateDto,
  SplPlayToneDto,
  SplStopToneDto,
} from '../dto/splDto'
import { toSafeNumber as num, toPaginated } from './commonAdapter'

// ===== DTO → Domain =====

/** calibration_data JSON blob 透传（后端按 Dict[str, Any] 原样存取，值不转换） */
function toCalibrationData(raw: Record<string, unknown> | null | undefined): CalibrationData | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  return raw as unknown as CalibrationData
}

/** SplMappingItemDto → SPLMapping（显式逐字段映射） */
export function toSPLMapping(dto: SplMappingItemDto): SPLMapping {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? undefined,
    deviceId: dto.device_id ?? undefined,
    device: dto.device as SPLMapping['device'],
    deviceName: dto.device_name ?? undefined,
    deviceModel: dto.device_model ?? undefined,
    deviceType: dto.device_type ?? undefined,
    distance: dto.distance ?? undefined,
    targetSpl: dto.target_spl ?? undefined,
    digitalGain: dto.digital_gain ?? undefined,
    calibrationStatus: (dto.calibration_status ?? undefined) as SPLMapping['calibrationStatus'],
    calibrationData: toCalibrationData(dto.calibration_data),
    isCurrent: dto.is_current ?? undefined,
    status: (dto.calibration_status ?? '') as SPLMapping['status'],
    createdAt: dto.created_at ?? undefined,
    updatedAt: dto.updated_at ?? undefined,
  }
}

/** SPL 分页列表 → SPL 分页 Domain（复用 commonAdapter.toPaginated） */
export function toSPLMappingList(dto: SplMappingListDto | null | undefined) {
  return toPaginated(dto, toSPLMapping)
}

/** SPL 统计 → SPLStats */
export function toSPLStats(dto: SplStatsDto | null | undefined): SPLStats {
  return {
    total: num(dto?.total),
    calibrated: num(dto?.calibrated),
    uncalibrated: num(dto?.uncalibrated),
    associatedDevices: num(dto?.associated_devices),
  }
}

function toSPLHistoryItem(dto: SplHistoryItemDto): SPLHistoryItem {
  return {
    id: dto.id,
    calibrationData: toCalibrationData(dto.calibration_data),
    distance: dto.distance ?? undefined,
    testFrequency: dto.test_frequency ?? undefined,
    createdAt: dto.created_at ?? undefined,
  }
}

/** 校准历史 → SPLHistoryList */
export function toSPLHistory(dto: SplHistoryDto | null | undefined): SPLHistoryList {
  return {
    items: (dto?.items ?? []).map(toSPLHistoryItem),
    total: dto?.total ?? 0,
  }
}

function toSPLByDeviceItem(dto: SplByDeviceItemDto): SPLByDeviceItem {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? undefined,
    deviceId: dto.device_id ?? undefined,
    deviceType: dto.device_type ?? undefined,
    distance: dto.distance ?? undefined,
    targetSpl: dto.target_spl ?? undefined,
    calibrationStatus: dto.calibration_status ?? undefined,
    createdAt: dto.created_at ?? undefined,
    updatedAt: dto.updated_at ?? undefined,
  }
}

/** 按设备的 SPL 映射 → SPLByDeviceList */
export function toSPLByDevice(dto: SplByDeviceDto | null | undefined): SPLByDeviceList {
  return {
    items: (dto?.items ?? []).map(toSPLByDeviceItem),
    total: dto?.total ?? 0,
  }
}

// ===== Domain → DTO（查询参数/请求体） =====

/**
 * SPL 列表查询 → snake_case query
 * 后端 SPLMappingQueryRequest：keyword / search / calibration_status / page /
 * per_page / device_id
 */
export function toSPLQueryDto(query: SPLQuery): SplQueryDto {
  const params: SplQueryDto = {}
  if (query.keyword) params.keyword = query.keyword
  if (query.calibrationStatus) params.calibration_status = query.calibrationStatus
  if (query.status) params.calibration_status = query.status
  if (query.page !== undefined) params.page = query.page
  if (query.perPage !== undefined) params.per_page = query.perPage
  if (query.deviceId !== undefined && query.deviceId !== '') params.device_id = Number(query.deviceId)
  return params
}

/**
 * SPL 创建/更新请求体：camelCase 表单 → snake_case DTO。
 * 接受 Partial<SPLMapping> 与增益点编辑器的混合表单（digital_gain /
 * calibrationData.points 内的后端原值键整块透传）。
 */
export function toSPLUpsertDto(
  input: Partial<SPLMapping> & {
    digital_gain?: number | null
    calibration_status?: string
  },
  mode: 'create' | 'update' = 'create'
): SplCreateDto | SplUpdateDto {
  const calibrationData = input.calibrationData
    ? (input.calibrationData as unknown as Record<string, unknown>)
    : undefined

  if (mode === 'create') {
    const dto: SplCreateDto = {
      name: input.name ?? '',
      description: input.description ?? null,
      device_id: input.deviceId !== undefined ? Number(input.deviceId) : null,
      device_type: input.deviceType ?? null,
      distance: input.distance ?? null,
      target_spl: input.targetSpl ?? null,
      digital_gain: (input as { digital_gain?: number | null }).digital_gain ?? null,
      test_frequency: input.testFrequency ?? null,
      calibration_status: (input as { calibration_status?: string }).calibration_status ?? null,
      calibration_data: calibrationData ?? null,
    }
    return dto
  }

  const dto: SplUpdateDto = {
    name: input.name ?? null,
    description: input.description ?? null,
    device_id: input.deviceId !== undefined ? Number(input.deviceId) : null,
    device_type: input.deviceType ?? null,
    distance: input.distance ?? null,
    target_spl: input.targetSpl ?? null,
    digital_gain: (input as { digital_gain?: number | null }).digital_gain ?? null,
    test_frequency: input.testFrequency ?? null,
    calibration_status: (input as { calibration_status?: string }).calibration_status ?? null,
    calibration_data: calibrationData ?? null,
    is_current: input.isCurrent ?? null,
  }
  return dto
}

/** 测试音播放入参 → SplPlayToneDto */
export function toSPLPlayToneDto(input: SPLPlayToneInput): SplPlayToneDto {
  return {
    gain_value: input.gainValue,
    gain_offset: input.gainOffset,
    target_spl: input.targetSpl,
    unique_id: input.uniqueId,
  }
}

/** 停止测试音入参 → SplStopToneDto */
export function toSPLStopToneDto(uniqueId?: string | null): SplStopToneDto {
  return { unique_id: uniqueId ?? undefined }
}

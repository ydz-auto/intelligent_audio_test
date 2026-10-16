/**
 * 物理域 SPL DTO→Domain 适配器（infrastructure/adapters 层；16_设备域.md §10 契约）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；Presentation 层不感知 snake_case。
 */
import type {
  CalibrationPoint,
  SplCalibrationData,
  SplDeviceType,
  SplHistoryItem,
  SplMapping,
  SplStats,
} from '@/domain/models/splMapping'
import type {
  CalibrationDataDto,
  CalibrationPointDto,
  SplHistoryItemDto,
  SplMappingItemDto,
  SplStatsDto,
} from '@/infrastructure/dto/spl.dto'

const DEVICE_TYPE_SET: ReadonlySet<string> = new Set(['dry', 'noise'])

/** device_type 归一：非 dry/noise 回 null（§4.2 徽章口径） */
export function toSplDeviceType(type: string | null): SplDeviceType | null {
  if (!type || !DEVICE_TYPE_SET.has(type)) return null
  return type as SplDeviceType
}

/** 校准状态归一：非 calibrated 一律按未校准展示（§4.2 两态口径） */
export function toCalibrationStatus(
  status: string | null
): 'calibrated' | 'uncalibrated' | null {
  if (!status) return null
  return status === 'calibrated' ? 'calibrated' : 'uncalibrated'
}

export function calibrationPointFromDto(
  dto: CalibrationPointDto
): CalibrationPoint {
  return {
    spl: dto.spl,
    gainOffset: dto.gain_offset,
    digitalGain: dto.digital_gain,
    baseLevel: dto.base_level,
    finalLevel: dto.final_level,
  }
}

export function calibrationDataFromDto(
  dto: CalibrationDataDto | null
): SplCalibrationData | null {
  if (!dto) return null
  return { points: (dto.points ?? []).map(calibrationPointFromDto) }
}

export function splMappingFromDto(dto: SplMappingItemDto): SplMapping {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description,
    deviceId: dto.device_id,
    deviceName: dto.device_name,
    deviceModel: dto.device_model,
    deviceType: toSplDeviceType(dto.device_type),
    distance: dto.distance,
    targetSpl: dto.target_spl,
    digitalGain: dto.digital_gain,
    calibrationStatus: toCalibrationStatus(dto.calibration_status),
    testFrequency: dto.test_frequency,
    calibrationData: calibrationDataFromDto(dto.calibration_data),
    isCurrent: dto.is_current,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

export function splStatsFromDto(dto: SplStatsDto): SplStats {
  return {
    total: dto.total,
    calibrated: dto.calibrated,
    uncalibrated: dto.uncalibrated,
    associatedDevices: dto.associated_devices,
  }
}

export function splHistoryItemFromDto(dto: SplHistoryItemDto): SplHistoryItem {
  return {
    id: dto.id,
    calibrationData: calibrationDataFromDto(dto.calibration_data),
    distance: dto.distance,
    testFrequency: dto.test_frequency,
    createdAt: dto.created_at,
  }
}

/**
 * 数字域 RMS-SPL DTO→Domain 适配器（infrastructure/adapters 层；16_设备域.md §10 契约）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；Presentation 层不感知 snake_case。
 */
import type {
  ApiCalibrationPoint,
  ApiConfigRef,
  ApiRmsSplMapping,
  DigitalSplProtocol,
} from '@/domain/models/digitalSpl'
import type { CalibrationStatus } from '@/domain/models/splMapping'
import type {
  ApiCalibrationPointDto,
  ApiConfigRefDto,
  ApiRmsSplMappingDto,
} from '@/infrastructure/dto/digital-spl.dto'
import { toCalibrationStatus } from '@/infrastructure/adapters/splAdapter'

const PROTOCOL_SET: ReadonlySet<string> = new Set(['websocket', 'http'])

/** protocol 归一：非 websocket/http 回 null（§4.3 协议徽章） */
export function toDigitalSplProtocol(
  protocol: string | null
): DigitalSplProtocol | null {
  if (!protocol || !PROTOCOL_SET.has(protocol)) return null
  return protocol as DigitalSplProtocol
}

export function apiCalibrationPointFromDto(
  dto: ApiCalibrationPointDto
): ApiCalibrationPoint {
  return {
    targetSpl: dto.target_spl,
    gainLinear: dto.gain_linear,
    rmsDbfs: dto.rms_dbfs,
  }
}

/** calibration_data.points → 数字域点集（target_spl/gain_linear/rms_dbfs 子集） */
export function digitalCalibrationPointsFromDto(
  dto: ApiRmsSplMappingDto['calibration_data']
): ApiCalibrationPoint[] {
  const points = dto?.points ?? []
  return points
    .filter(
      (point): point is ApiCalibrationPointDto & { target_spl: number; gain_linear: number } =>
        typeof point?.target_spl === 'number' && typeof point?.gain_linear === 'number'
    )
    .map((point) => ({
      targetSpl: point.target_spl,
      gainLinear: point.gain_linear,
      rmsDbfs: point.rms_dbfs ?? null,
    }))
}

export function apiRmsSplMappingFromDto(dto: ApiRmsSplMappingDto): ApiRmsSplMapping {
  return {
    id: dto.id,
    apiId: dto.api_id,
    name: dto.name,
    description: dto.description,
    vendor: dto.vendor,
    protocol: toDigitalSplProtocol(dto.protocol),
    referenceSpl: dto.reference_spl,
    referenceGainLinear: dto.reference_gain_linear,
    calibrationStatus: toCalibrationStatus(dto.calibration_status),
    calibrationPoints: digitalCalibrationPointsFromDto(dto.calibration_data),
    minGainLinear: dto.min_gain_linear,
    maxGainLinear: dto.max_gain_linear,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

export function apiConfigRefFromDto(dto: ApiConfigRefDto): ApiConfigRef {
  return {
    id: dto.id,
    name: dto.name,
    vendor: dto.vendor,
    protocol: dto.protocol,
    rmsSplMappingId: dto.rms_spl_mapping_id,
  }
}

export type { CalibrationStatus }

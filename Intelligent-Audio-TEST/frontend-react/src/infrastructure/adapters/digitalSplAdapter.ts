/**
 * 数字域 RMS-SPL DTO→Domain 适配器（infrastructure/adapters 层；16_设备域.md §10 契约）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；Presentation 层不感知 snake_case。
 * 读侧字段 calibration_points（平铺点集）；写侧请求体用 calibration_data.points（全量替换）。
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
  ApiRmsCalibrationDataDto,
  ApiRmsSplCalibrateDto,
  ApiRmsSplCreateDto,
  ApiRmsSplMappingDto,
  ApiRmsSplSetDefaultDto,
  ApiRmsSplUpdateDto,
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

/** 读侧 calibration_points 平铺点集 → 数字域点集（target_spl/gain_linear/rms_dbfs 子集） */
export function digitalCalibrationPointsFromDto(
  points: ApiRmsSplMappingDto['calibration_points']
): ApiCalibrationPoint[] {
  return (points ?? [])
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
    calibrationPoints: digitalCalibrationPointsFromDto(dto.calibration_points),
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
    protocol: dto.protocol ?? null,
    rmsSplMappingId: dto.rms_spl_mapping_id,
  }
}

export type { CalibrationStatus }

/* ───────────────────── Domain → DTO（请求体 snake_case） ───────────────────── */

/** 数字域点集 → calibration_data 写侧结构（points 全量替换） */
export function digitalCalibrationDataFromDomain(
  points: ApiCalibrationPoint[] | null | undefined
): ApiRmsCalibrationDataDto | null {
  if (!points) return null
  return {
    points: points.map((point) => ({
      target_spl: point.targetSpl,
      gain_linear: point.gainLinear,
      rms_dbfs: point.rmsDbfs ?? null,
    })),
  }
}

/** 数字域创建请求体（RmsSplMappingCreateRequest；apiId 必填） */
export function digitalSplCreateRequestFromDomain(
  input: Omit<ApiRmsSplMapping, 'id' | 'createdAt' | 'updatedAt'>
): ApiRmsSplCreateDto {
  return {
    api_id: input.apiId,
    name: input.name,
    description: input.description,
    vendor: input.vendor,
    protocol: input.protocol,
    reference_spl: input.referenceSpl,
    reference_gain_linear: input.referenceGainLinear,
    calibration_status: input.calibrationStatus,
    calibration_data: digitalCalibrationDataFromDomain(input.calibrationPoints),
    min_gain_linear: input.minGainLinear,
    max_gain_linear: input.maxGainLinear,
  }
}

/** 数字域更新请求体（RmsSplMappingUpdateRequest；后端 exclude_none 丢弃 null） */
export function digitalSplUpdateRequestFromDomain(
  patch: Partial<ApiRmsSplMapping>
): ApiRmsSplUpdateDto {
  return {
    name: patch.name ?? null,
    description: patch.description ?? null,
    vendor: patch.vendor ?? null,
    protocol: patch.protocol ?? null,
    reference_spl: patch.referenceSpl ?? null,
    reference_gain_linear: patch.referenceGainLinear ?? null,
    calibration_status: patch.calibrationStatus ?? null,
    calibration_data: digitalCalibrationDataFromDomain(patch.calibrationPoints),
    min_gain_linear: patch.minGainLinear ?? null,
    max_gain_linear: patch.maxGainLinear ?? null,
  }
}

/** 数字域校准请求体（RmsSplCalibrateRequest；空点集回退 { points: [] } 保持契约） */
export function digitalSplCalibrateRequestFromDomain(
  points: ApiCalibrationPoint[]
): ApiRmsSplCalibrateDto {
  return {
    calibration_data: digitalCalibrationDataFromDomain(points) ?? { points: [] },
  }
}

/** 设默认/清除默认请求体（RmsSplSetDefaultRequest；mapping_id 空/0 清除） */
export function digitalSplSetDefaultRequestFromDomain(
  mappingId: number | null
): ApiRmsSplSetDefaultDto {
  return { mapping_id: mappingId }
}

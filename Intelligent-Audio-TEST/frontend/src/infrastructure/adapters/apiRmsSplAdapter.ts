/**
 * ApiRmsSpl Adapter —— ApiRmsSplDto(snake_case) ⇄ ApiRmsSplMapping(camelCase)
 */
import type {
  ApiRmsSplMapping,
  ApiCalibrationPoint,
  ApiRmsSplQuery,
  ApiRmsSplUpsertInput,
} from '../../domain/model/apiRmsSpl'
import type {
  ApiRmsSplMappingItemDto,
  ApiRmsSplCreateDto,
  ApiRmsSplUpdateDto,
  ApiRmsSplCalibrateDto,
  ApiRmsSplSetDefaultDto,
} from '../dto/apiRmsSplDto'
import { toSafeNumber as num } from './commonAdapter'

// ===== DTO → Domain =====

function toCalibrationPoints(
  raw: ApiRmsSplMappingItemDto['calibration_points']
): ApiCalibrationPoint[] {
  return (raw || []).map((p) => ({
    targetSpl: num(p.target_spl),
    gainLinear: num(p.gain_linear),
    rmsDbfs: p.rms_dbfs ?? undefined,
  }))
}

export function toApiRmsSplMapping(dto: ApiRmsSplMappingItemDto): ApiRmsSplMapping {
  return {
    id: dto.id,
    apiId: dto.api_id,
    name: dto.name ?? undefined,
    vendor: dto.vendor ?? undefined,
    protocol: dto.protocol ?? undefined,
    referenceSpl: dto.reference_spl ?? undefined,
    referenceGainLinear: dto.reference_gain_linear ?? undefined,
    calibrationStatus: dto.calibration_status ?? undefined,
    calibrationPoints: toCalibrationPoints(dto.calibration_points),
    minGainLinear: dto.min_gain_linear ?? undefined,
    maxGainLinear: dto.max_gain_linear ?? undefined,
    isCalibrated: dto.is_calibrated ?? undefined,
  }
}

export function toApiRmsSplMappingList(
  dtos: ApiRmsSplMappingItemDto[] | null | undefined
): ApiRmsSplMapping[] {
  return (dtos || []).map(toApiRmsSplMapping)
}

// ===== Domain → DTO（请求体） =====

function toCalibrationDataDto(
  points: ApiCalibrationPoint[] | undefined
): Record<string, unknown> | undefined {
  if (!points) return undefined
  return {
    points: points.map((p) => ({
      target_spl: p.targetSpl,
      gain_linear: p.gainLinear,
      rms_dbfs: p.rmsDbfs ?? null,
    })),
  }
}

export function toApiRmsSplCreateDto(input: ApiRmsSplUpsertInput): ApiRmsSplCreateDto {
  return {
    api_id: Number(input.apiId),
    name: input.name,
    description: input.description,
    vendor: input.vendor,
    protocol: input.protocol,
    reference_spl: input.referenceSpl,
    reference_gain_linear: input.referenceGainLinear,
    calibration_status: input.calibrationStatus,
    calibration_data: toCalibrationDataDto(input.calibrationPoints),
    min_gain_linear: input.minGainLinear,
    max_gain_linear: input.maxGainLinear,
  }
}

export function toApiRmsSplUpdateDto(input: ApiRmsSplUpsertInput): ApiRmsSplUpdateDto {
  return {
    name: input.name,
    description: input.description,
    vendor: input.vendor,
    protocol: input.protocol,
    reference_spl: input.referenceSpl,
    reference_gain_linear: input.referenceGainLinear,
    calibration_status: input.calibrationStatus,
    calibration_data: toCalibrationDataDto(input.calibrationPoints),
    min_gain_linear: input.minGainLinear,
    max_gain_linear: input.maxGainLinear,
  }
}

export function toApiRmsSplQueryDto(query: ApiRmsSplQuery): Record<string, unknown> {
  return {
    page: query.page,
    per_page: query.perPage,
    api_id: query.apiId,
    calibration_status: query.calibrationStatus,
  }
}

export function toApiRmsSplCalibrateDto(
  calibrationPoints: ApiCalibrationPoint[]
): ApiRmsSplCalibrateDto {
  return { calibration_data: toCalibrationDataDto(calibrationPoints) || { points: [] } }
}

export function toApiRmsSplSetDefaultDto(
  mappingId: string | number | null | undefined
): ApiRmsSplSetDefaultDto {
  return { mapping_id: mappingId == null ? null : Number(mappingId) }
}

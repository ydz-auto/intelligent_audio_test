/**
 * 物理域 SPL DTO→Domain 适配器（infrastructure/adapters 层；16_设备域.md §10 契约）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；Presentation 层不感知 snake_case。
 */
import { CALIBRATION_BASE_LEVEL_DBFS } from '@/domain/models/splMapping'
import type {
  CalibrationPoint,
  PlaybackDeviceRef,
  SplCalibrationData,
  SplDeviceType,
  SplHistoryItem,
  SplMapping,
  SplStats,
  SplTestToneInput,
} from '@/domain/models/splMapping'
import type {
  CalibrationDataDto,
  CalibrationPointDto,
  SplCalibrationResultDto,
  SplHistoryItemDto,
  SplMappingCreateDto,
  SplMappingItemDto,
  SplMappingUpdateDto,
  SplStatsDto,
  SplTestToneRequestDto,
  SplTestToneStopRequestDto,
} from '@/infrastructure/dto/spl.dto'
import type { PlaybackDeviceItemDto } from '@/infrastructure/dto/playback-device.dto'
import { toPlaybackDeviceType } from '@/infrastructure/adapters/playbackDeviceAdapter'

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

/** 增益偏移可为 0.1 步进小数，浮点加法尾差在展示前收敛到 0.01 dB */
function roundDb(value: number): number {
  return Math.round(value * 100) / 100
}

/**
 * 校准点归一。后端模拟校准写入键为 `gain`（device_service calibrate 落库
 * `{"gain": n, "spl": x}`，INT-1503 DB 实证），前端表单写入键为 `gainOffset`；两者都认。
 * 缺省字段按 §6.7 口径推导：数字增益 = 增益偏移，基础电平 -30 dBFS，最终电平 = 基础 + 偏移。
 */
export function calibrationPointFromDto(
  dto: CalibrationPointDto
): CalibrationPoint {
  const gainOffset = dto.gainOffset ?? dto.gain ?? null
  return {
    spl: dto.spl ?? null,
    gainOffset,
    digitalGain: dto.digitalGain ?? gainOffset,
    baseLevel:
      dto.baseLevel ?? (gainOffset == null ? null : CALIBRATION_BASE_LEVEL_DBFS),
    finalLevel:
      dto.finalLevel ??
      (gainOffset == null
        ? null
        : roundDb(CALIBRATION_BASE_LEVEL_DBFS + gainOffset)),
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

/** 播放设备列表项 → 播放设备引用（GET /playback-devices → SplMappingPage 关联播放设备 facet） */
export function playbackDeviceRefFromPlaybackDto(
  dto: PlaybackDeviceItemDto
): PlaybackDeviceRef {
  return {
    id: dto.id,
    name: dto.name,
    model: dto.model,
    deviceType: toPlaybackDeviceType(dto.device_type),
  }
}

/** 物理域校准结果（SplCalibrationResult → 页面可读形状） */
export function splCalibrationResultFromDto(
  dto: SplCalibrationResultDto
): { success: true; calibrationStatus: 'calibrated' | 'uncalibrated' } {
  return {
    success: true,
    calibrationStatus:
      dto.calibration_status === 'calibrated' ? 'calibrated' : 'uncalibrated',
  }
}

/* ───────────────────── Domain → DTO（请求体 snake_case） ───────────────────── */

/** 校准点集：camelCase 表单 → 存储键（与读侧 wire 契约一致：后端 calibration_data.points 为 camelCase JSONB 透传，Vue 亦写 camelCase） */
export function calibrationDataToDto(
  data: SplCalibrationData | null | undefined
): CalibrationDataDto | null {
  if (!data) return null
  return {
    points: (data.points ?? []).map((point) => ({
      spl: point.spl,
      gainOffset: point.gainOffset,
      digitalGain: point.digitalGain,
      baseLevel: point.baseLevel,
      finalLevel: point.finalLevel,
    })),
  }
}

/**
 * 物理域创建请求体（SPLMappingCreateRequest；isCurrent 不在创建契约内，跳过）。
 * deviceName/deviceModel 由后端按 device_id 关联派生，不入请求体。
 */
export function splMappingCreateRequestFromDomain(
  input: Omit<
    SplMapping,
    'id' | 'createdAt' | 'updatedAt' | 'deviceName' | 'deviceModel'
  >
): SplMappingCreateDto {
  return {
    name: input.name,
    description: input.description,
    device_id: input.deviceId,
    device_type: input.deviceType,
    distance: input.distance,
    target_spl: input.targetSpl,
    digital_gain: input.digitalGain,
    test_frequency: input.testFrequency,
    calibration_status: input.calibrationStatus,
    calibration_data: calibrationDataToDto(input.calibrationData),
  }
}

/** 测试音播放请求体（PlayTestToneRequest；后端 exclude_none 丢弃 null，缺省取 schema 默认 50/65） */
export function splTestToneRequestFromDomain(
  input: SplTestToneInput
): SplTestToneRequestDto {
  return {
    gain_value: input.gainValue,
    gain_offset: input.gainOffset,
    target_spl: input.targetSpl,
    unique_id: input.uniqueId,
  }
}

/** 测试音停止请求体（StopTestToneRequest；unique_id 为空则以空体表达「停止全部」） */
export function splTestToneStopRequestFromDomain(
  uniqueId: string | null
): SplTestToneStopRequestDto {
  return { unique_id: uniqueId }
}

/**
 * 物理域更新请求体（SPLMappingUpdateRequest；后端 exclude_none 丢弃 null，
 * 故校准数据显式清除（null）时以空点集 { points: [] } 表达「重置校准」语义）。
 */
export function splMappingUpdateRequestFromDomain(
  patch: Partial<SplMapping>
): SplMappingUpdateDto {
  return {
    name: patch.name ?? null,
    description: patch.description ?? null,
    device_id: patch.deviceId ?? null,
    device_type: patch.deviceType ?? null,
    distance: patch.distance ?? null,
    target_spl: patch.targetSpl ?? null,
    digital_gain: patch.digitalGain ?? null,
    test_frequency: patch.testFrequency ?? null,
    calibration_status: patch.calibrationStatus ?? null,
    calibration_data:
      patch.calibrationData === null
        ? { points: [] }
        : calibrationDataToDto(patch.calibrationData),
    is_current: patch.isCurrent ?? null,
  }
}

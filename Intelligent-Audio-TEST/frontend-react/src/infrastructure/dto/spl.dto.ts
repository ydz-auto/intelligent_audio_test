/**
 * 物理域 SPL DTO（infrastructure/dto 层；顶层字段 snake_case 与 api_gateway/schemas/spl.py 对齐）。
 * 展示层不感知 snake_case；字段映射统一在 adapters/splAdapter.ts。
 * 例外：calibration_data.points 实机 wire 契约为 camelCase（后端 device_service
 * `_spl_mapping_to_dict` 直传 DB JSONB，且不含 digital_gain），与 Vue 侧 useSplMapping 消费口径一致。
 */

export interface CalibrationPointDto {
  spl: number | null
  /** 前端/表单写入键（camelCase 原样透传 JSONB） */
  gainOffset?: number | null
  /** 后端模拟校准写入键（device_service calibrate 写 `{"gain": n, "spl": x}`，INT-1503 实测） */
  gain?: number | null
  digitalGain?: number | null
  baseLevel?: number | null
  finalLevel?: number | null
}

export interface CalibrationDataDto {
  points: CalibrationPointDto[]
}

/** SplMappingItem（schemas/spl.py:67-84 实测） */
export interface SplMappingItemDto {
  id: number
  name: string
  description: string | null
  device_id: number | null
  device: Record<string, unknown> | null
  device_name: string | null
  device_model: string | null
  device_type: string | null
  distance: number | null
  target_spl: number | null
  digital_gain: number | null
  calibration_status: string | null
  test_frequency: number | null
  calibration_data: CalibrationDataDto | null
  is_current: boolean | null
  created_at: string | null
  updated_at: string | null
}

/** SplStatsData（schemas/spl.py:104-109 实测） */
export interface SplStatsDto {
  total: number
  calibrated: number
  uncalibrated: number
  associated_devices: number
}

/** SplHistoryItem（schemas/spl.py:91-97 实测） */
export interface SplHistoryItemDto {
  id: number
  calibration_data: CalibrationDataDto | null
  distance: number | null
  test_frequency: number | null
  created_at: string | null
}

/** SplHistoryData（schemas/spl.py:99-102；INT-297 统一列表信封） */
export interface SplHistoryDto {
  items: SplHistoryItemDto[]
  total: number
}

/** SplMappingListData = PaginatedData[SplMappingItem]（schemas/spl.py:87-89） */
export interface SplMappingListDto {
  items: SplMappingItemDto[]
  total: number
  page?: number
  per_page?: number
  pages?: number
}

/** 物理域创建请求（schemas/spl.py:29-40 SPLMappingCreateRequest） */
export interface SplMappingCreateDto {
  name: string
  description: string | null
  device_id: number | null
  device_type: string | null
  distance: number | null
  target_spl: number | null
  digital_gain: number | null
  test_frequency: number | null
  calibration_status: string | null
  calibration_data: CalibrationDataDto | null
}

/** 物理域更新请求（schemas/spl.py:42-53 SPLMappingUpdateRequest） */
export interface SplMappingUpdateDto {
  name: string | null
  description: string | null
  device_id: number | null
  device_type: string | null
  distance: number | null
  target_spl: number | null
  digital_gain: number | null
  test_frequency: number | null
  calibration_status: string | null
  calibration_data: CalibrationDataDto | null
  is_current: boolean | null
}

/** 物理域校准结果（schemas/spl.py:145-148 SplCalibrationResult） */
export interface SplCalibrationResultDto {
  id: number
  calibration_status: string
}

/** 测试音播放请求（schemas/spl.py:56-60 PlayTestToneRequest） */
export interface SplTestToneRequestDto {
  gain_value: number
  gain_offset: number | null
  target_spl: number | null
  unique_id: string | null
}

/** 测试音停止请求（schemas/spl.py:63-64 StopTestToneRequest） */
export interface SplTestToneStopRequestDto {
  unique_id: string | null
}

/** 播放设备引用（GET /playback-devices 子集） */
export interface PlaybackDeviceRefDto {
  id: number
  name: string
  model: string | null
  device_type: string | null
}

/**
 * SPL（声压级映射）DTO —— snake_case
 * 对应后端 api_gateway/schemas/spl.py::SplMappingItem / SplMappingListData /
 * SplHistoryItem / SplHistoryData / SplStatsData / SplByDeviceItem /
 * SplByDeviceData，及各请求体 Schema
 */
import type { PaginatedDto } from './common'

/** 对应后端 SplMappingItem（calibration_data 为整块 JSON） */
export interface SplMappingItemDto {
  id: number
  name: string
  description?: string | null
  device_id?: number | null
  device?: Record<string, unknown> | null
  device_name?: string | null
  device_model?: string | null
  device_type?: string | null
  distance?: number | null
  target_spl?: number | null
  digital_gain?: number | null
  calibration_status?: string | null
  test_frequency?: number | null
  calibration_data?: Record<string, unknown> | null
  is_current?: boolean | null
  created_at?: string | null
  updated_at?: string | null
}

/** 对应后端 SplMappingListData = PaginatedData[SplMappingItem] */
export type SplMappingListDto = PaginatedDto<SplMappingItemDto>

/** 对应后端 SplHistoryItem */
export interface SplHistoryItemDto {
  id: number
  calibration_data?: Record<string, unknown> | null
  distance?: number | null
  test_frequency?: number | null
  created_at?: string | null
}

/** 对应后端 SplHistoryData */
export interface SplHistoryDto {
  items: SplHistoryItemDto[]
  total: number
}

/** 对应后端 SplStatsData */
export interface SplStatsDto {
  total: number
  calibrated: number
  uncalibrated: number
  associated_devices: number
}

/** 对应后端 SplByDeviceItem */
export interface SplByDeviceItemDto {
  id: number
  name: string
  description?: string | null
  device_id?: number | null
  device_type?: string | null
  distance?: number | null
  target_spl?: number | null
  calibration_status?: string | null
  created_at?: string | null
  updated_at?: string | null
}

/** 对应后端 SplByDeviceData */
export interface SplByDeviceDto {
  items: SplByDeviceItemDto[]
  total: number
}

// ===== 请求体/查询参数（snake_case） =====

/** 对应后端 SPLMappingQueryRequest（search 为 keyword 别名） */
export interface SplQueryDto {
  keyword?: string
  search?: string
  calibration_status?: string
  page?: number
  per_page?: number
  device_id?: number
}

/** 对应后端 SPLMappingCreateRequest */
export interface SplCreateDto {
  name: string
  description?: string | null
  device_id?: number | null
  device_type?: string | null
  distance?: number | null
  target_spl?: number | null
  digital_gain?: number | null
  test_frequency?: number | null
  calibration_status?: string | null
  calibration_data?: Record<string, unknown> | null
}

/** 对应后端 SPLMappingUpdateRequest */
export interface SplUpdateDto {
  name?: string | null
  description?: string | null
  device_id?: number | null
  device_type?: string | null
  distance?: number | null
  target_spl?: number | null
  digital_gain?: number | null
  test_frequency?: number | null
  calibration_status?: string | null
  calibration_data?: Record<string, unknown> | null
  is_current?: boolean | null
}

/** 对应后端 PlayTestToneRequest */
export interface SplPlayToneDto {
  gain_value?: number
  gain_offset?: number
  target_spl?: number
  unique_id?: string
}

/** 对应后端 StopTestToneRequest */
export interface SplStopToneDto {
  unique_id?: string
}

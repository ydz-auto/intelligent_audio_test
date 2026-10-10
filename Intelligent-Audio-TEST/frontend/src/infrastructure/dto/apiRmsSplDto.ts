/**
 * ApiRmsSplMapping（被测 API 数字域 RMS→SPL 映射）DTO —— snake_case
 * 对应后端 api_test_service api_rms_spl_mappings 行经网关透传结构
 */
import type { PaginatedDto } from './common'

/** 对应后端 _mapping_to_dict（api_rms_spl_config_service） */
export interface ApiRmsSplMappingItemDto {
  id: number
  api_id: number
  name?: string | null
  vendor?: string | null
  protocol?: string | null
  reference_spl?: number | null
  reference_gain_linear?: number | null
  calibration_status?: string | null
  calibration_points?: Array<{
    target_spl: number
    gain_linear: number
    rms_dbfs?: number | null
  }> | null
  min_gain_linear?: number | null
  max_gain_linear?: number | null
  is_calibrated?: boolean | null
}

export type ApiRmsSplMappingListDto = PaginatedDto<ApiRmsSplMappingItemDto>

export interface ApiRmsSplByApiDto {
  items: ApiRmsSplMappingItemDto[]
  total: number
}

/** 创建请求体（snake_case） */
export interface ApiRmsSplCreateDto {
  api_id: number
  name?: string
  description?: string
  vendor?: string
  protocol?: string
  reference_spl?: number
  reference_gain_linear?: number
  calibration_status?: string
  calibration_data?: Record<string, unknown>
  min_gain_linear?: number
  max_gain_linear?: number
}

/** 更新请求体（snake_case） */
export interface ApiRmsSplUpdateDto {
  name?: string
  description?: string
  vendor?: string
  protocol?: string
  reference_spl?: number
  reference_gain_linear?: number
  calibration_status?: string
  calibration_data?: Record<string, unknown>
  min_gain_linear?: number
  max_gain_linear?: number
}

/** 校准请求体（snake_case） */
export interface ApiRmsSplCalibrateDto {
  calibration_data: Record<string, unknown>
}

/** 设置默认映射请求体（snake_case） */
export interface ApiRmsSplSetDefaultDto {
  mapping_id?: number | null
}

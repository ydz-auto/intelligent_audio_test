/**
 * 数字域 RMS-SPL DTO（infrastructure/dto 层；snake_case 与 api_gateway/schemas/api_rms_spl.py
 * + api_test_service ApiRmsSplMappingPO 对齐）。展示层不感知 snake_case；
 * 字段映射统一在 adapters/digitalSplAdapter.ts。
 */

/** 数字域校准点（§6.10：target_spl ↔ gain_linear ↔ rms_dbfs） */
export interface ApiCalibrationPointDto {
  target_spl: number
  gain_linear: number
  rms_dbfs: number | null
}

/** 数字域校准点集（RmsSplCalibrateRequest calibration_data） */
export interface ApiRmsCalibrationDataDto {
  points: ApiCalibrationPointDto[]
}

/** ApiRmsSplMappingPO（api_models.py:50-72 实测） */
export interface ApiRmsSplMappingDto {
  id: number
  api_id: number
  name: string | null
  description: string | null
  vendor: string | null
  protocol: string | null
  reference_spl: number | null
  reference_gain_linear: number | null
  calibration_status: string | null
  calibration_data: ApiRmsCalibrationDataDto | null
  min_gain_linear: number | null
  max_gain_linear: number | null
  created_at: string | null
  updated_at: string | null
}

/** 被测 API 引用（GET /apis 子集 + rmsSplMappingId 默认指针） */
export interface ApiConfigRefDto {
  id: number
  name: string
  vendor: string | null
  protocol: string | null
  rms_spl_mapping_id: number | null
}

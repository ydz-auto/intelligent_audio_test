/**
 * 数字域 RMS-SPL DTO（infrastructure/dto 层；snake_case 与 api_gateway/schemas/api_rms_spl.py
 * + api_test_service ApiRmsSplMappingPO 对齐）。展示层不感知 snake_case；
 * 字段映射统一在 adapters/digitalSplAdapter.ts。
 */

/** 数字域校准点（INT-2081：target_spl ↔ rms_dbfs，gain_linear 由 dBFS 推导） */
export interface ApiCalibrationPointDto {
  target_spl: number
  gain_linear: number
  rms_dbfs: number | null
}

/** 数字域校准点集（RmsSplCalibrateRequest calibration_data） */
export interface ApiRmsCalibrationDataDto {
  points: ApiCalibrationPointDto[]
}

/** ApiRmsSplMappingPO（api_models.py:50-72 + api_rms_spl_config_service.py:31-53 实测） */
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
  /** 读侧字段名 calibration_points（平铺点集；写侧请求体用 calibration_data.points，见 ApiRmsSplCalibrateDto） */
  calibration_points: ApiCalibrationPointDto[]
  min_gain_linear: number | null
  max_gain_linear: number | null
  created_at: string | null
  updated_at: string | null
}

/** 数字域列表响应（ApiRmsSplMappingListData，分页信封） */
export interface ApiRmsSplMappingListDto {
  items: ApiRmsSplMappingDto[]
  total: number
  page?: number
  per_page?: number
  pages?: number
}

/** 数字域创建请求（schemas/api_rms_spl.py:14-26 RmsSplMappingCreateRequest） */
export interface ApiRmsSplCreateDto {
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
}

/** 数字域更新请求（schemas/api_rms_spl.py:28-39 RmsSplMappingUpdateRequest） */
export interface ApiRmsSplUpdateDto {
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
}

/** 数字域校准请求（schemas/api_rms_spl.py:41-43 RmsSplCalibrateRequest；点集全量替换） */
export interface ApiRmsSplCalibrateDto {
  calibration_data: ApiRmsCalibrationDataDto
}

/** 设默认/清除默认请求（schemas/api_rms_spl.py:45-47 RmsSplSetDefaultRequest；mapping_id 空/0 清除） */
export interface ApiRmsSplSetDefaultDto {
  mapping_id: number | null
}

/** 被测 API 引用（GET /apis 子集 + rmsSplMappingId 默认指针） */
export interface ApiConfigRefDto {
  id: number
  name: string
  vendor: string | null
  protocol: string | null
  rms_spl_mapping_id: number | null
}

/**
 * ApiRmsSplMapping（被测 API 数字域 RMS→SPL 映射）领域模型 —— camelCase
 * 对应后端 api_gateway/application/services/api_rms_spl/（经 gRPC 透传
 * api_test_service ApiRmsSplConfigService）
 *
 * 与 SPLMapping（物理设备域，domain/model/spl.ts）对称：
 * 校准对象是被测 API（数字音频输入灵敏度），而非物理音箱。
 */

/** 单条校准测量点：目标 SPL ↔ 线性增益 ↔ 实测 RMS dBFS */
export interface ApiCalibrationPoint {
  targetSpl: number
  gainLinear: number
  rmsDbfs?: number
}

/** API RMS→SPL 映射（对应后端 api_rms_spl_mappings 行） */
export interface ApiRmsSplMapping {
  id: string | number
  apiId: string | number
  name?: string
  vendor?: string
  protocol?: string
  /** 参考声压级（未校准时基准，默认 65 dB SPL） */
  referenceSpl?: number
  /** 参考线性增益（默认 1.0） */
  referenceGainLinear?: number
  /** 校准状态（值 = CalibrationStatus 枚举原值） */
  calibrationStatus?: 'calibrated' | 'uncalibrated' | (string & {})
  /** 校准测量点（后端 calibration_data.points） */
  calibrationPoints?: ApiCalibrationPoint[]
  minGainLinear?: number
  maxGainLinear?: number
  isCalibrated?: boolean
}

/** 映射列表查询条件（camelCase；API 层转 snake_case） */
export interface ApiRmsSplQuery {
  page?: number
  perPage?: number
  apiId?: string | number
  calibrationStatus?: string
}

/** 分页结果（与设备域 SPL 分页同构） */
export interface ApiRmsSplMappingList {
  items: ApiRmsSplMapping[]
  total: number
  page: number
  perPage: number
  pages: number
}

/** 映射创建/更新入参（camelCase Domain） */
export interface ApiRmsSplUpsertInput {
  apiId?: string | number
  name?: string
  description?: string
  vendor?: string
  protocol?: string
  referenceSpl?: number
  referenceGainLinear?: number
  calibrationStatus?: string
  calibrationPoints?: ApiCalibrationPoint[]
  minGainLinear?: number
  maxGainLinear?: number
}

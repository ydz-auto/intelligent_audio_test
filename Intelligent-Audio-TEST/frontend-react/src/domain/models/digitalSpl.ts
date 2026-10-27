/**
 * 数字域 RMS-SPL 映射（API/Realtime 灵敏度域）领域模型（domain 层；16_设备域.md §4.3 落位）。
 * 形态对照 api_test_service ApiRmsSplMappingPO 实测 + api_gateway/schemas/api_rms_spl.py
 * RmsSplMappingCreateRequest 字段：api_id/name/description/vendor/protocol/reference_spl/
 * reference_gain_linear/calibration_status/calibration_data/min_gain_linear/max_gain_linear。
 * 数字域校准点 = {target_spl, gain_linear, rms_dbfs}（§6.10）。
 */

import type { CalibrationStatus } from '@/domain/models/splMapping'

/** 数字域协议（protocol 默认 websocket） */
export type DigitalSplProtocol = 'websocket' | 'http'

/** 数字域校准点（INT-2081：目标SPL ↔ 实测 dBFS，线性增益为推导值） */
export interface ApiCalibrationPoint {
  /** 目标声压级（dB SPL，0~120） */
  targetSpl: number
  /** 线性增益（>0，由 dBFS 与基础电平 -30 dBFS 推导） */
  gainLinear: number
  /** 实测 RMS（dBFS，必填 -120~0；主输入） */
  rmsDbfs: number | null
}

/** 数字域校准点集（calibration_data，提交全量替换） */
export interface ApiRmsCalibrationData {
  points: ApiCalibrationPoint[]
}

/** 数字域 RMS-SPL 映射 */
export interface ApiRmsSplMapping {
  id: number
  /** 关联被测 API（必填 1:N） */
  apiId: number
  name: string | null
  description: string | null
  vendor: string | null
  protocol: DigitalSplProtocol | null
  /** 参考声压级（30-120，默认 65，未校准基准） */
  referenceSpl: number | null
  /** 参考线性增益（正数，默认 1.0） */
  referenceGainLinear: number | null
  calibrationStatus: CalibrationStatus | null
  calibrationPoints: ApiCalibrationPoint[]
  /** 增益下限（默认 0.001，防静音限幅） */
  minGainLinear: number | null
  /** 增益上限（默认 10.0，防爆音限幅） */
  maxGainLinear: number | null
  createdAt: string | null
  updatedAt: string | null
}

/** 被测 API 引用（关联 API facet/默认指针；GET /apis 子集 + rmsSplMappingId 指针） */
export interface ApiConfigRef {
  id: number
  name: string
  vendor: string | null
  protocol: string | null
  /** 该 API 当前默认映射指针（apis.rms_spl_mapping_id；命中则映射为默认） */
  rmsSplMappingId: number | null
}

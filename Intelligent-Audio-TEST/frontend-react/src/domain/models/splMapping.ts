/**
 * 声压级映射（物理域，设备 SPL/E2E）领域模型（domain 层；16_设备域.md §4.2 落位）。
 * 形态对照 api_gateway/schemas/spl.py SplMappingItem 实测：
 * id/name/description/device_id/device_name/device_model/device_type/distance/target_spl/
 * digital_gain/calibration_status/test_frequency/calibration_data/is_current/created_at/updated_at。
 * 展示层只见 camelCase Domain；snake_case 转换落在 infrastructure/adapters/splAdapter.ts。
 */

/** 校准状态（calibration_status；已校准/未校准两态，§4.2 徽章依据） */
export type CalibrationStatus = 'calibrated' | 'uncalibrated'

/** 播放设备类型（device_type dry/noise → 干声/噪声，§4.2 徽章依据） */
export type SplDeviceType = 'dry' | 'noise'

/** 校准点（CalibrationPointSchema 实测五字段） */
export interface CalibrationPoint {
  /** 实测声压级（SPL，dB） */
  spl: number | null
  /** 增益偏移（dB，-12~+25） */
  gainOffset: number | null
  /** 数字增益（dB） */
  digitalGain: number | null
  /** 基础电平（dBFS，只读「-30」） */
  baseLevel: number | null
  /** 最终电平（dBFS，只读） */
  finalLevel: number | null
}

/** 校准点集（CalibrationDataSchema） */
export interface SplCalibrationData {
  points: CalibrationPoint[]
}

/** 物理域 SPL 映射（SplMappingItem） */
export interface SplMapping {
  id: number
  name: string
  description: string | null
  deviceId: number | null
  deviceName: string | null
  deviceModel: string | null
  deviceType: SplDeviceType | null
  /** 测量距离（米，默认 1.0） */
  distance: number | null
  /** 目标声压级（dB） */
  targetSpl: number | null
  /** 数字增益（dB） */
  digitalGain: number | null
  calibrationStatus: CalibrationStatus | null
  /** 测试频率（Hz，默认 1000） */
  testFrequency: number | null
  calibrationData: SplCalibrationData | null
  isCurrent: boolean | null
  createdAt: string | null
  updatedAt: string | null
}

/** 物理域统计（GET /spl/stats，SplStatsData 四字段实测） */
export interface SplStats {
  total: number
  calibrated: number
  uncalibrated: number
  /** 未删除映射 device_id distinct */
  associatedDevices: number
}

/** 校准历史项（GET /spl/{id}/history，SplHistoryItem 实测） */
export interface SplHistoryItem {
  id: number
  calibrationData: SplCalibrationData | null
  distance: number | null
  testFrequency: number | null
  createdAt: string | null
}

/**
 * 测试音播放入参（§6.5；POST /spl/test-tone → PlayTestToneRequest
 * gain_value/gain_offset/target_spl/unique_id，V9.7.10 handleTestSPL 同源）。
 * gain_value 为硬件增益刻度 0-100（V9.7.10 `50 + gainOffset / 0.24` 换算）。
 */
export interface SplTestToneInput {
  /** 硬件增益刻度（gain_value，默认 50） */
  gainValue: number
  /** 增益偏移（dB，gain_offset） */
  gainOffset: number | null
  /** 目标声压级（dB，target_spl，缺省后端 65） */
  targetSpl: number | null
  /** 播放设备系统唯一标识（unique_id） */
  uniqueId: string | null
}

/** 播放设备引用（关联播放设备 facet/列渲染；GET /playback-devices 子集） */
export interface PlaybackDeviceRef {
  id: number
  name: string
  model: string | null
  deviceType: SplDeviceType | null
}

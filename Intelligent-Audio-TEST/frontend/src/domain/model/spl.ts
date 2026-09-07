/**
 * SPL（声压级校准）领域模型 —— camelCase
 * 对应后端 api_gateway/schemas/spl.py::SplMappingItem / SplHistoryItem /
 * SplStatsData / SplByDeviceItem / SplMappingListData
 *
 * 后端序列化输出为 snake_case（APIModel，serialize_by_alias=False），
 * Infrastructure 层 adapter 负责字段名转换，本层零后端依赖。
 */

/** 校准数据点（后端 calibration_data JSON 内的 points 元素，值保持后端原样） */
export interface CalibrationPoint {
  input: number
  output: number
  splValue: number
  /** 增益偏移量（历史数据以 gainOffset 或 gain 表达，读取时优先 gainOffset） */
  gainOffset?: number
  gain?: number
  spl?: number
  measuredSpl?: number
  targetSpl?: number
  frequency?: number
  db?: number
  linearGain?: number
  /** 后端原值字段名（增益点编辑器提交时保留） */
  digital_gain?: number | null
  createdAt?: string
}

/** 校准数据（对应后端 SplMappingItem.calibration_data JSON 对象） */
export interface CalibrationData {
  id?: string | number
  mappingId?: string | number
  points?: CalibrationPoint[]
  createdAt?: string
  updatedAt?: string
  method?: string
  notes?: string
  minDb?: number
  maxDb?: number
  mode?: 'linear' | 'db_curve'
}

/** SPL 映射校准状态（后端 calibration_status 字段原值） */
export type SPLMappingStatus = 'active' | 'inactive' | 'calibrating' | (string & {})

/** SPL 映射（对应后端 SplMappingItem） */
export interface SPLMapping {
  id: string | number
  name: string
  description?: string
  deviceId?: string | number
  /** 关联设备信息（后端 device JSON 对象） */
  device?: import('./device').PlaybackDevice & Record<string, unknown>
  deviceName?: string
  deviceModel?: string
  deviceType?: string
  distance?: number
  targetSpl?: number
  /** 数字增益（后端原值字段 digital_gain） */
  digitalGain?: number
  testFrequency?: number
  calibrationStatus?: 'calibrated' | 'uncalibrated' | (string & {})
  calibrationData?: CalibrationData
  /** 是否当前映射（对应后端 is_current，仅更新接口回显） */
  isCurrent?: boolean
  status: SPLMappingStatus
  createdAt?: string
  updatedAt?: string
  lastCalibratedAt?: string
  gain1Spl?: number
  gain50Spl?: number
  gain100Spl?: number
  measurementDate?: string
}

/** SPL 映射列表查询条件（前端 Domain，camelCase；发往后端时由 API 层转 snake_case） */
export interface SPLQuery {
  keyword?: string
  deviceId?: string | number
  calibrationStatus?: string
  status?: string
  page?: number
  perPage?: number
  sortBy?: string
  order?: 'asc' | 'desc'
}

/** SPL 统计（对应后端 SplStatsData） */
export interface SPLStats {
  total: number
  calibrated: number
  uncalibrated: number
  associatedDevices: number
}

/** 校准历史项（对应后端 SplHistoryItem） */
export interface SPLHistoryItem {
  id: number
  calibrationData?: CalibrationData
  distance?: number
  testFrequency?: number
  createdAt?: string
}

/** 校准历史（对应后端 SplHistoryData） */
export interface SPLHistoryList {
  items: SPLHistoryItem[]
  total: number
}

/** 按设备的 SPL 映射项（对应后端 SplByDeviceItem） */
export interface SPLByDeviceItem {
  id: number
  name: string
  description?: string
  deviceId?: number
  deviceType?: string
  distance?: number
  targetSpl?: number
  calibrationStatus?: string
  createdAt?: string
  updatedAt?: string
}

/** 按设备的 SPL 映射列表（对应后端 SplByDeviceData） */
export interface SPLByDeviceList {
  items: SPLByDeviceItem[]
  total: number
}

/** 测试音播放入参（对应后端 PlayTestToneRequest） */
export interface SPLPlayToneInput {
  gainValue?: number
  gainOffset?: number
  targetSpl?: number
  uniqueId?: string
}

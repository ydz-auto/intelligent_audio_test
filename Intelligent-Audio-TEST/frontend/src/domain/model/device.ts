/**
 * Device（测试设备）领域模型 —— camelCase
 * 对应后端 api_gateway/schemas/device.py::DeviceItem / DeviceStatusItem /
 * DeviceScanItem / DeviceHealthItem
 *
 * 枚举值保持后端原值（如 'online' / 'offline' / 'testing'），只转字段名。
 */

import type { DeviceStatusType } from '../enums'

/** 测试设备系统类型（后端 system 字段原值） */
export type DeviceSystem = 'android' | 'ios' | 'harmony' | (string & {})

/** 设备唯一标识兜底归一字段（serial / serial_number / device_id / device_unique_id / id） */
export type DeviceIdentifierField =
  | 'serial'
  | 'serialNumber'
  | 'deviceId'
  | 'deviceUniqueId'
  | 'id'

/** 测试设备连接类型（后端 connection_type 字段原值） */
export type DeviceConnectionType = 'usb' | 'wifi' | (string & {})

/** 测试设备状态（后端 status 字段原值；枚举常量单一来源见 domain/enums.ts::DeviceStatus） */
export type DeviceStatus = DeviceStatusType

/** 提示词音频配置（后端 prompt_config，JSON 对象） */
export interface DevicePromptConfig {
  [key: string]: unknown
}

/** 测试设备完整模型（对应 DeviceItem） */
export interface Device {
  id: string | number
  name: string
  model?: string
  description?: string
  /** 设备类型（后端 type 字段原值） */
  type?: string
  /** 系统类型：android / ios / harmony */
  system?: DeviceSystem
  systemVersion?: string
  appName?: string
  appVersion?: string
  location?: string
  /** 单条音频最大时长（秒） */
  maxAudioDuration?: number
  /** 是否需要提示词音频 */
  needsPromptAudio?: boolean
  promptConfig?: DevicePromptConfig
  connectionType?: DeviceConnectionType
  /** 驱动关键字（逗号分隔字符串，后端原值为 string） */
  keywords?: string
  serialNumber?: string
  ip?: string
  status?: DeviceStatus
  lastOnlineAt?: string
  createdAt?: string
  updatedAt?: string
  /** 设备侧驱动名称 */
  driverName?: string
  /** 支持的算法类型列表 */
  supportedAlgorithms?: string[]
  /** 前端本地选中态（非后端契约） */
  selected?: boolean
}

/** 设备状态项（对应 DeviceStatusItem / DeviceHealthItem，轮询与健康检查用） */
export interface DeviceStatusInfo {
  id: string | number
  name: string
  status?: DeviceStatus
  lastOnlineAt?: string
  model?: string
  system?: DeviceSystem
}

/** 扫描到的设备（对应 DeviceScanItem / PlaybackScanItem，serial 为后端原值字段） */
export interface ScannedDevice {
  /** 设备序列号（后端 DeviceScanItem.serial / PlaybackScanItem.device_unique_id） */
  serial?: string
  model?: string
  system?: DeviceSystem
  status?: DeviceStatus
  isRegistered?: boolean
  id?: string
  name?: string
  type?: string
  systemVersion?: string
  appName?: string
  appVersion?: string
  ip?: string
  /** 设备唯一 ID（后端 device_unique_id / device_id，播放设备扫描链路） */
  deviceUniqueId?: string
  /** 采样率（后端 sample_rate，播放设备扫描链路） */
  sampleRate?: number
  /** 通道索引（后端 channel_index，播放设备扫描链路） */
  channelIndex?: number
}

/** 设备测试响应（对应 DeviceTestData） */
export interface DeviceTestData {
  id: string | number
  status: DeviceStatus
  wakeupCommand?: string
}

/** 播放设备（对应 PlaybackDeviceItem；枚举值保持后端原值） */
export interface PlaybackDevice {
  id: string | number
  name: string
  model?: string
  /** 设备类型：dry / noise / prompt（后端 device_type 原值） */
  type?: 'dry' | 'noise' | 'prompt' | (string & {})
  deviceType?: string
  sampleRate?: number
  channelIndex?: number
  deviceUniqueId?: string
  description?: string
  status?: DeviceStatus
  currentSplMappingId?: number
  createdAt?: string
  updatedAt?: string
  /** 设备唯一标识兜底来源（serial / serialNumber / deviceId / deviceUniqueId / id，非后端契约） */
  identifierField?: DeviceIdentifierField
}

/** 扫描结果 / 已添加设备的统一显示模型（DTO 多别名兜底归一，camelCase） */
export interface ScannedDeviceDisplayItem {
  /** 归一化唯一标识（兜底链见 deviceAdapter.normalizeScannedDevice） */
  displayKey: string | number | undefined
  /** 设备序列号（后端 serial / serial_number / device_id / device_unique_id 兜底归一） */
  serial?: string | number
  /** 设备唯一 ID（后端 device_unique_id / device_id / id / name 兜底归一） */
  deviceUniqueId: string | number | undefined
  name: string
  model: string
  /** 系统类型（后端 system / platform 兜底归一） */
  system?: DeviceSystem
  /** 系统版本（后端 system_version / version / os_version 兜底归一） */
  systemVersion?: string
  /** 采样率（后端 sample_rate） */
  sampleRate?: number
  /** 通道索引（后端 channel_index） */
  channelIndex?: number
}

/** 可用设备详情（serials 接口扫描出的物理设备） */
export interface AvailableSerialDevice {
  serial?: string
  model?: string
  system?: DeviceSystem
  status?: DeviceStatus
  ip?: string
  name?: string
  type?: string
  systemVersion?: string
  appName?: string
  appVersion?: string
}

/** 已注册驱动关键字（对应后端 /test-devices/driver-keywords 响应项，camelCase） */
export interface DriverKeyword {
  /** 驱动名称 */
  name: string
  /** 系统类型（android / ios 等，后端 system 原值） */
  system: string
  /** 关键字列表（逗号分隔后端原值 → Domain 数组） */
  keywords: string[]
}

// ===== 设备管理页 UI 扩展视图（原 views/Device/deviceTypes.ts 内联定义收敛） =====

/**
 * 测试设备（管理页 UI 扩展视图）
 * Device 领域模型 + 前端分组标记；domain 层禁止索引签名兜底，
 * 原由 [key: string]: any 承载的零散展示字段经 DeviceCard 的
 * DeviceLike（any）插槽渲染，不进入本契约。
 */
export interface TestDeviceView extends Device {
  /** 前端分组标记（fetchAllDevices 写入：'测试设备' / 'API设备'） */
  category?: string
}

/**
 * API 设备（管理页 UI 扩展视图）
 * 数据源为 APIConfig（apisApi.getAll），按设备卡片统一展示。
 */
export interface ApiDeviceView extends Device {
  /** 前端分组标记（fetchAllDevices 写入：'API设备'） */
  category?: string
  /** 供应方 */
  vendor?: string
  /** API 端点列表（fetchAllDevices 归一化 endpoint/url 兜底） */
  endpoints?: { endpoint: string; url?: string }[]
  /** 关联算法类型 */
  algorithmType?: string
}

/** 设备管理页三个 tab 的统一联合类型（测试设备 / API设备 / 播放设备） */
export type DeviceUnion = TestDeviceView | ApiDeviceView | PlaybackDevice

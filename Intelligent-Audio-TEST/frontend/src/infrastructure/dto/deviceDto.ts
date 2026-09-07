/**
 * Device（测试设备）/ PlaybackDevice（播放设备）DTO —— snake_case
 * 对应后端 api_gateway/schemas/device.py / playback.py
 */

/** 创建/更新设备的请求体（snake_case，显式映射自 Device 的 camelCase 字段） */
export type DeviceUpsertDto = {
  name?: string
  model?: string
  type?: string
  system?: string
  system_version?: string
  app_name?: string
  app_version?: string
  description?: string
  location?: string
  max_audio_duration?: number
  needs_prompt_audio?: boolean
  prompt_config?: Record<string, unknown>
  connection_type?: string
  keywords?: string
  serial_number?: string
  ip?: string
  status?: string
  supported_algorithms?: string[]
}

/** 对应 DeviceItem（serialize_by_alias=False 输出 snake_case） */
export interface DeviceItemDto {
  id: number | string
  name: string
  model?: string
  description?: string
  type?: string
  system?: string
  system_version?: string
  app_name?: string
  app_version?: string
  location?: string
  max_audio_duration?: number
  needs_prompt_audio?: boolean
  prompt_config?: Record<string, unknown>
  connection_type?: string
  keywords?: string
  serial_number?: string
  ip?: string
  status?: string
  last_online_at?: string
  created_at?: string
  updated_at?: string
  driver_name?: string
  supported_algorithms?: string[]
}

/** 对应 DeviceListData（PaginatedData[DeviceItem]） */
export interface DeviceListDto extends PaginatedBaseDto {
  items: DeviceItemDto[]
}

/** 分页基础字段（与 dto/common.ts PaginatedDto 一致） */
interface PaginatedBaseDto {
  total: number
  page: number
  per_page: number
  pages: number
}

/** 对应 DeviceStatusItem / DeviceHealthItem */
export interface DeviceStatusItemDto {
  id: number | string
  name: string
  status?: string
  last_online_at?: string
  model?: string
  system?: string
}

/** 对应 DeviceStatusListData { items, total } */
export interface DeviceStatusListDto {
  items: DeviceStatusItemDto[]
  total: number
}

/** 对应 DeviceScanItem */
export interface DeviceScanItemDto {
  serial?: string
  model?: string
  system?: string
  status?: string
  is_registered?: boolean
  id?: string
  name?: string
  type?: string
  system_version?: string
  app_name?: string
  app_version?: string
  ip?: string
}

/** 对应 DeviceTestData */
export interface DeviceTestDataDto {
  id: number | string
  status: string
  wakeup_command?: string
}

/** 对应 PlaybackDeviceItem */
export interface PlaybackDeviceItemDto {
  id: number | string
  name: string
  model?: string
  device_type?: string
  sample_rate?: number
  channel_index?: number
  device_unique_id?: string
  description?: string
  status?: string
  current_spl_mapping_id?: number
  created_at?: string
  updated_at?: string
}

/** 对应 PlaybackDeviceListData（PaginatedData[PlaybackDeviceItem]） */
export interface PlaybackDeviceListDto extends PaginatedBaseDto {
  items: PlaybackDeviceItemDto[]
}

/** 对应 PlaybackScanItem */
export interface PlaybackScanItemDto {
  name?: string
  model?: string
  device_unique_id?: string
  channel_index?: number
  sample_rate?: number
  type?: string
  status?: string
}

/** 对应 PlaybackStatusItem */
export interface PlaybackStatusItemDto {
  id: number | string
  name: string
  unique_id: string
  status: string
  device_index?: number
}

/**
 * 扫描结果 / 已添加设备条目 DTO —— snake_case
 *
 * 后端多个接口（GET /playback-devices、GET /test-devices、POST /playback-devices/scan、
 * GET /test-devices/serials）字段别名不统一（serial 与 serial_number、
 * system_version 与 version/os_version、device_unique_id 与 device_id 并存），
 * 此处用宽松可选形状描述，具体兜底归一逻辑见 deviceAdapter.normalizeScannedDevice。
 */
export interface ScannedDeviceDto {
  id?: string | number
  name?: string
  model?: string
  /** 序列号（serial 别名） */
  serial?: string
  /** 序列号（serial_number 别名） */
  serial_number?: string
  /** 系统类型（platform 别名） */
  system?: string
  /** 系统版本（version 别名） */
  system_version?: string
  /** 系统版本（version 别名） */
  version?: string
  /** 系统版本（os_version 别名） */
  os_version?: string
  /** 系统类型（system 别名） */
  platform?: string
  /** 设备 ID（device_unique_id 别名） */
  device_id?: string
  /** 设备唯一 ID（device_id 别名） */
  device_unique_id?: string
  /** 采样率（sampleRate 的后端键名） */
  sample_rate?: number
  /** 通道索引（channelIndex 的后端键名） */
  channel_index?: number
}

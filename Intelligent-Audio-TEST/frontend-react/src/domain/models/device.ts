/**
 * 设备域领域模型（domain 层；10_测试执行.md §9 落位）。
 * 形态对照 api_gateway/schemas/device.py DeviceItem 实测：
 * id/name/model/description/type/system/system_version/serial_number/ip/status/
 * last_online_at/supported_algorithms/connection_type。
 * 混跑口径（§3.6.1）：device_type 三值 physical/http_api/websocket_api 同任务可选。
 */

/** 设备类型（device_type 三值，混跑徽章依据） */
export type DeviceType = 'physical' | 'http_api' | 'websocket_api'

export type DeviceStatus = 'online' | 'offline'

export interface Device {
  id: number
  name: string
  model: string | null
  description: string | null
  /** schema type 字段（device_type 三值之一） */
  type: DeviceType | null
  system: string | null
  systemVersion: string | null
  serialNumber: string | null
  ip: string | null
  status: DeviceStatus | null
  lastOnlineAt: string | null
  /** 算法过滤依据（supported_algorithms 实测） */
  supportedAlgorithms: string[] | null
  connectionType: string | null
}

/** 设备类型徽章元数据（§3.6.1 混跑：图标 + 中文文案） */
export const DEVICE_TYPE_META: Record<
  DeviceType,
  { label: string; short: string }
> = {
  physical: { label: '真机', short: 'physical' },
  http_api: { label: 'HTTP API', short: 'http_api' },
  websocket_api: { label: 'Realtime WS', short: 'websocket_api' },
}

/**
 * SSE 设备状态变更事件名（后端 shared.utils.redis_pubsub.EventType.DEVICE_STATUS_CHANGED，
 * 经 sse_bp._map_event 以同名推送到 DEVICE_EVENTS 通道）。
 * 载荷：{device_id, event_type, status, source, success, detail, timestamp}（snake_case 直出）。
 */
export const DEVICE_STATUS_CHANGED_EVENT = 'device_status_changed'

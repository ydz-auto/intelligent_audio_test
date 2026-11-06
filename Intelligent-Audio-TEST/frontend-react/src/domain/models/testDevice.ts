/**
 * 测试设备领域模型（domain 层；16_设备域.md §3.4 落位）。
 * 形态对照 api_gateway/schemas/device.py DeviceItem 实测逐字段。
 * 五态状态机（设备管理功能设计文档.md:179-183）：online/offline/connecting/disconnecting/error。
 * 「测试中」为占用叠加态（INT-487）：不占五态机枚举/筛选/统计，仅 occupied 承载本地瞬时态兜底。
 * 所属实验室 labId/labName（INT-487）：后端 DTO 待暴露 lab_id，字段落地前 mock 先行。
 */
export type DeviceConnectionType = 'usb' | 'remote'

export type DeviceFiveState =
  | 'online'
  | 'offline'
  | 'connecting'
  | 'disconnecting'
  | 'error'

/** 五态徽章色映射（§7 status-badge dotColorMap/textColorMap 语义） */
export const DEVICE_FIVE_STATE_META: Record<
  DeviceFiveState,
  { label: string; tone: 'success' | 'neutral' | 'info' | 'warning' | 'destructive' }
> = {
  online: { label: '在线', tone: 'success' },
  offline: { label: '离线', tone: 'neutral' },
  connecting: { label: '连接中', tone: 'info' },
  disconnecting: { label: '断开中', tone: 'warning' },
  error: { label: '错误', tone: 'destructive' },
}

export interface TestDevice {
  id: number
  name: string
  model: string | null
  description: string | null
  /** schema type 字段（physical/http_api/websocket_api，本页不展示，留待接线） */
  type: string | null
  /** DeviceSystem 归一值（iOS/Android/HarmonyOS） */
  system: string | null
  systemVersion: string | null
  /** API 级别（Android API级别/HarmonyOS API级别，随设备系统切换，§6.2/设备管理:262-278） */
  apiLevel: string | null
  appName: string | null
  appVersion: string | null
  connectionType: string | null
  serialNumber: string | null
  ip: string | null
  /** 高级设置（§6.2/设备管理:292-296：备注/标签/自定义属性/优先级） */
  remark: string | null
  tags: string[] | null
  customAttributes: string[] | null
  priority: number | null
  /** 五态状态机值；「测试中」不落此枚举 */
  status: DeviceFiveState | null
  lastOnlineAt: string | null
  driverName: string | null
  supportedAlgorithms: string[] | null
  needsPromptAudio: boolean | null
  maxAudioDuration: number | null
  location: string | null
  keywords: string | null
  /** 所属实验室（INT-487：待后端 DTO 暴露 lab_id，mock 先行） */
  labId: number | null
  labName: string | null
  /** 「测试中」占用态（INT-487：后端待暴露 occupied/testing，前端本地瞬时态兜底） */
  occupied: boolean
  createdAt: string | null
  updatedAt: string | null
}

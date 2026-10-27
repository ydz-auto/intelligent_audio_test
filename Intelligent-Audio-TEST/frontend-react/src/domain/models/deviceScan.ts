/**
 * 设备扫描领域模型（domain 层；16_设备域.md §6.1）。
 * 对照 api_gateway/schemas/device.py DeviceScanItem + playback.py PlaybackScanItem，
 * snake_case 直出（扫描端点不经 infra adapter 转换，feature 弹窗与 application 合并共用）。
 * INT-2074：开始测试页「扫描设备」勾选结果经 DeviceScanSelection 回传，
 * useResourceSelection.mergeScannedDevices 消费（未注册设备真实登记 + 勾选）。
 */

/** 扫描结果行（DeviceScanItem / PlaybackScanItem 字段并集） */
export interface DeviceScanRow {
  name?: string | null
  model?: string | null
  serial?: string | null
  system?: string | null
  system_version?: string | null
  ip?: string | null
  status?: string | null
  /** 已注册设备（测试设备扫描带；播放通道扫描恒缺省） */
  is_registered?: boolean
  /** 已注册时=数字 id；未注册测试设备=序列号字符串 */
  id?: number | string | null
  device_unique_id?: string | null
  channel_index?: number | null
  sample_rate?: number | null
  type?: string | null
  app_name?: string | null
  app_version?: string | null
  connection_type?: string | null
  connectionType?: string | null
}

/** 开始测试页扫描选择回传载荷（test + playback 两态） */
export interface DeviceScanSelection {
  test: DeviceScanRow[]
  playback: DeviceScanRow[]
}

/** 连接方式判定（§6.1/V9.7.10 ScanDevicesModal.vue:27-29）：
 * 后端透传 connection_type 优先；未透传时按 adb 远程序列号形态（host:port）或 ip 判定，
 * 否则按 USB 连接（与设备列表「连接方式」列同口径）。 */
export function resolveScanConnectionType(row: DeviceScanRow): { value: 'usb' | 'remote'; label: string } {
  const raw = row.connection_type ?? row.connectionType
  if (raw === 'usb') return { value: 'usb', label: 'USB连接' }
  if (raw === 'remote') return { value: 'remote', label: '远程连接' }
  if ((row.serial ?? '').includes(':') || row.ip) return { value: 'remote', label: '远程连接' }
  return { value: 'usb', label: 'USB连接' }
}

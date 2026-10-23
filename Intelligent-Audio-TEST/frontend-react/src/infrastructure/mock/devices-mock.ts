/**
 * 设备管理页 mock 常量（infrastructure 层）。
 * 设备/告警/分组/实验室等已切真实后端端点（devicesApi 接线 INT-644/INT-655），
 * 本文件仅保留后端未覆盖的数据源：
 * - DeviceStatsPoint / MOCK_DEVICE_STATS：历史监控统计分析 vChart 采点（无实时监控指标端点）
 * 其余 mock 数据（测试/播放设备、告警、分组、状态历史、实验室）已删除，避免 mock/api 双口径并存。
 */

/* ==================== 历史监控统计分析（§3.7：可用性/性能/错误/使用统计 vChart 区） ==================== */

/** 统计分析采点（设备管理:411-429；mock 日粒度时间序列，接线后换实时监控指标端点） */
export interface DeviceStatsPoint {
  date: string
  availability: number
  cpu: number
  memory: number
  battery: number
  errors: number
  operations: number
}

export const MOCK_DEVICE_STATS: DeviceStatsPoint[] = [
  { date: '10-11', availability: 96, cpu: 38, memory: 52, battery: 78, errors: 1, operations: 4 },
  { date: '10-12', availability: 98, cpu: 41, memory: 55, battery: 74, errors: 0, operations: 6 },
  { date: '10-13', availability: 94, cpu: 47, memory: 61, battery: 69, errors: 2, operations: 5 },
  { date: '10-14', availability: 99, cpu: 35, memory: 48, battery: 82, errors: 0, operations: 8 },
  { date: '10-15', availability: 97, cpu: 44, memory: 58, battery: 71, errors: 1, operations: 7 },
  { date: '10-16', availability: 95, cpu: 52, memory: 66, battery: 63, errors: 3, operations: 9 },
  { date: '10-17', availability: 93, cpu: 49, memory: 62, battery: 66, errors: 2, operations: 10 },
]

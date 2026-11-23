/**
 * 设备监控统计 DTO（infrastructure/dto 层——snake_case 唯一出现层；
 * 《设备监控统计与播放设备控制接口契约》§1.2）。
 * GET /test-devices/monitor-stats 实测响应 data：
 * { granularity, start_date, end_date, device_count, points[{date, availability, cpu,
 *   memory, battery, errors, operations, health_check_samples}] }。
 */
export interface DeviceMonitorStatsPointDto {
  /** ISO 日期 YYYY-MM-DD（区间内每天都有，无数据日也返回） */
  date: string
  availability: number | null
  cpu: number | null
  memory: number | null
  battery: number | null
  errors: number
  operations: number
  health_check_samples: number
}

export interface DeviceMonitorStatsDto {
  granularity: string
  start_date: string
  end_date: string
  device_count: number
  points: DeviceMonitorStatsPointDto[]
}

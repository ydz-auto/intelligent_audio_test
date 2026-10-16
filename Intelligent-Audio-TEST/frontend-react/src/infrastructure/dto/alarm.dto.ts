/**
 * 设备监控告警 DTO（infrastructure/dto 层——snake_case 唯一出现层；16_设备域.md §3.7/§6.6）。
 * 形态对照 device_bp 告警族端点（GET /alarms /alarm-rules /status-history）+ common_enums 枚举。
 * get_alarm_stats 实测 stats：active/acknowledged/resolved/total。
 */
import type { AlarmMetricType, AlarmSeverity, AlarmStatus } from '@/domain/models/alarm'

/** GET /alarms 告警项（device_bp AlarmItem 实测字段） */
export interface AlarmDto {
  id: number
  device_id: number | null
  device_name: string | null
  rule_id: number | null
  rule_name: string | null
  metric_type: AlarmMetricType | null
  content: string | null
  trigger_value: number | null
  threshold_value: number | null
  email_sent: boolean
  email_error: string | null
  status: AlarmStatus | null
  severity: AlarmSeverity | null
  acknowledged_by: string | null
  created_at: string | null
}

/** GET /alarms 响应内 data.stats（get_alarm_stats 实测） */
export interface AlarmStatsDto {
  active: number
  acknowledged: number
  resolved: number
  total: number
}

/** GET /alarm-rules 告警规则项（device.py AlarmRuleCreateSchema 字段集） */
export interface AlarmRuleDto {
  id: number
  name: string
  metric_type: AlarmMetricType
  threshold_value: number
  severity: AlarmSeverity
  notify_email: boolean
  enabled: boolean
  created_at: string | null
  updated_at: string | null
}

/** GET /status-history 状态历史项（device.py DeviceStatusHistoryQuery 字段集） */
export interface DeviceStatusHistoryDto {
  id: number
  device_id: number | null
  device_name: string | null
  event_type: string | null
  from_status: string | null
  to_status: string | null
  source: string | null
  result: string | null
  detail: string | null
  created_at: string | null
}

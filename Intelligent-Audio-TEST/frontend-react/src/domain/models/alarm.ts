/**
 * 设备监控告警域领域模型（domain 层；16_设备域.md §3.7/§6.6 落位）。
 * 形态对照 shared/models/common_enums.py AlarmMetricType/AlarmSeverity/AlarmStatus/
 * DeviceStatusEventType 实测 + device_bp 告警/状态历史端点字段。
 * 告警指标中文映射（AlarmMetricType 实测）：offline_duration→「离线时长」/health_check_failures→
 * 「连续健康检查失败次数」/cpu→「CPU 使用率(%)」/memory→「内存使用率(%)」/battery→「电量(%)」。
 */
export type AlarmSeverity = 'critical' | 'warning' | 'info'

export type AlarmStatus = 'active' | 'acknowledged' | 'resolved'

export type AlarmMetricType =
  | 'offline_duration'
  | 'health_check_failures'
  | 'cpu'
  | 'memory'
  | 'battery'

export const ALARM_SEVERITY_META: Record<
  AlarmSeverity,
  { label: string; tone: 'destructive' | 'warning' | 'info' }
> = {
  critical: { label: '严重', tone: 'destructive' },
  warning: { label: '警告', tone: 'warning' },
  info: { label: '提示', tone: 'info' },
}

export const ALARM_METRIC_META: Record<AlarmMetricType, { label: string; unit: string }> = {
  offline_duration: { label: '离线时长', unit: '分钟' },
  health_check_failures: { label: '连续健康检查失败次数', unit: '次' },
  cpu: { label: 'CPU 使用率', unit: '%' },
  memory: { label: '内存使用率', unit: '%' },
  battery: { label: '电量', unit: '%' },
}

export const ALARM_STATUS_META: Record<
  AlarmStatus,
  { label: string; tone: 'warning' | 'info' | 'neutral' }
> = {
  active: { label: '待处理', tone: 'warning' },
  acknowledged: { label: '已确认', tone: 'info' },
  resolved: { label: '已恢复', tone: 'neutral' },
}

export interface Alarm {
  id: number
  deviceId: number | null
  deviceName: string | null
  ruleId: number | null
  ruleName: string | null
  metricType: AlarmMetricType | null
  content: string | null
  triggerValue: number | null
  thresholdValue: number | null
  emailSent: boolean
  emailError: string | null
  status: AlarmStatus | null
  severity: AlarmSeverity | null
  acknowledgedBy: string | null
  createdAt: string | null
}

export interface AlarmStats {
  active: number
  acknowledged: number
  resolved: number
  total: number
}

export interface AlarmRule {
  id: number
  name: string
  metricType: AlarmMetricType
  thresholdValue: number
  severity: AlarmSeverity
  notifyEmail: boolean
  enabled: boolean
  createdAt: string | null
  updatedAt: string | null
}

/** 状态历史事件类型（INT-80 + §3.7 扩为四类历史承载） */
export type DeviceStatusEventType =
  | 'online'
  | 'offline'
  | 'connecting'
  | 'disconnecting'
  | 'error'
  | 'health_check'
  | 'operation'

export const DEVICE_EVENT_TYPE_META: Record<
  DeviceStatusEventType,
  { label: string }
> = {
  online: { label: '上线' },
  offline: { label: '离线' },
  connecting: { label: '连接中' },
  disconnecting: { label: '断开中' },
  error: { label: '错误' },
  health_check: { label: '健康检查' },
  operation: { label: '操作' },
}

export interface DeviceStatusEvent {
  id: number
  deviceId: number | null
  deviceName: string | null
  eventType: DeviceStatusEventType
  fromStatus: string | null
  toStatus: string | null
  source: string | null
  result: 'success' | 'failed' | null
  detail: string | null
  createdAt: string | null
}

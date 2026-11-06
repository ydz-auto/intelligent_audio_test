/**
 * 告警/状态历史 DTO→Domain 适配器（infrastructure/adapters 层；16_设备域.md §3.7/§6.6）。
 * 消费 alarm.dto.ts snake_case 类型，产出 domain 模型；event_type/severity/status 归一校验。
 */
import type {
  Alarm,
  AlarmRule,
  AlarmStatus,
  AlarmSeverity,
  AlarmMetricType,
  DeviceStatusEvent,
  DeviceStatusEventType,
} from '@/domain/models/alarm'
import type {
  AlarmDto,
  AlarmRuleDto,
  DeviceStatusHistoryDto,
} from '@/infrastructure/dto/alarm.dto'

const SEVERITY_SET: ReadonlySet<string> = new Set(['critical', 'warning', 'info'])
const STATUS_SET: ReadonlySet<string> = new Set(['active', 'acknowledged', 'resolved'])
const METRIC_SET: ReadonlySet<string> = new Set([
  'offline_duration',
  'health_check_failures',
  'cpu',
  'memory',
  'battery',
])
const EVENT_TYPE_SET: ReadonlySet<string> = new Set([
  'online',
  'offline',
  'connecting',
  'disconnecting',
  'error',
  'health_check',
  'operation',
])

export function alarmFromDto(dto: AlarmDto): Alarm {
  return {
    id: dto.id,
    deviceId: dto.device_id,
    deviceName: dto.device_name,
    ruleId: dto.rule_id,
    ruleName: dto.rule_name,
    metricType: dto.metric_type && METRIC_SET.has(dto.metric_type)
      ? (dto.metric_type as AlarmMetricType)
      : null,
    content: dto.content,
    triggerValue: dto.trigger_value,
    thresholdValue: dto.threshold_value,
    emailSent: dto.email_sent,
    emailError: dto.email_error,
    status: dto.status && STATUS_SET.has(dto.status) ? (dto.status as AlarmStatus) : null,
    severity: dto.severity && SEVERITY_SET.has(dto.severity)
      ? (dto.severity as AlarmSeverity)
      : null,
    acknowledgedBy: dto.acknowledged_by,
    createdAt: dto.created_at,
  }
}

export function alarmRuleFromDto(dto: AlarmRuleDto): AlarmRule {
  return {
    id: dto.id,
    name: dto.name,
    metricType: METRIC_SET.has(dto.metric_type)
      ? (dto.metric_type as AlarmMetricType)
      : 'offline_duration',
    thresholdValue: dto.threshold_value,
    severity: SEVERITY_SET.has(dto.severity) ? (dto.severity as AlarmSeverity) : 'warning',
    notifyEmail: dto.notify_email,
    enabled: dto.enabled,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

function formatDetailValue(value: unknown): string {
  if (value == null) return '—'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}

/**
 * status-history detail 归一（P2-5）。
 * 后端 `GET /status-history` 的 detail 是自由 JSON：字符串，或对象
 * （{"serial_number":"..."} / {"operation":"install_app","error":"..."}）。
 * 直接当 React 子节点渲染对象会抛 React #31 整页崩溃，因此在 infrastructure 层落成可读文本
 * （对象按 `key: value` 拼接，嵌套值 JSON 化），domain 侧只保留 string。
 */
export function formatStatusDetail(
  detail: string | Record<string, unknown> | null | undefined
): string | null {
  if (detail == null) return null
  if (typeof detail === 'string') {
    const text = detail.trim()
    return text.length > 0 ? text : null
  }
  if (Array.isArray(detail)) {
    return detail.length > 0 ? JSON.stringify(detail) : null
  }
  const entries = Object.entries(detail)
  if (entries.length === 0) return null
  return entries.map(([key, value]) => `${key}: ${formatDetailValue(value)}`).join('；')
}

export function statusEventFromDto(dto: DeviceStatusHistoryDto): DeviceStatusEvent {
  const eventType = dto.event_type && EVENT_TYPE_SET.has(dto.event_type)
    ? (dto.event_type as DeviceStatusEventType)
    : 'operation'
  return {
    id: dto.id,
    deviceId: dto.device_id,
    deviceName: dto.device_name,
    eventType,
    fromStatus: dto.from_status,
    toStatus: dto.to_status,
    source: dto.source,
    result: dto.result === 'success' || dto.result === 'failed' ? dto.result : null,
    detail: formatStatusDetail(dto.detail),
    createdAt: dto.created_at,
  }
}

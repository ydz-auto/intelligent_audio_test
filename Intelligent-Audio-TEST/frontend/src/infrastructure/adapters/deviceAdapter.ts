/**
 * Device / PlaybackDevice Adapter —— DTO(snake_case) → Domain(camelCase)
 *
 * 后端契约：api_gateway/schemas/device.py / playback.py。
 * 本文件是 device 相关接口唯一允许做 snake_case → camelCase 键名转换的地方。
 * ReadModel 定义在 domain/model/device.ts，本文件只做转换。
 */
import type {
  DeviceItemDto,
  DeviceStatusItemDto,
  DeviceScanItemDto,
  DeviceTestDataDto,
  PlaybackDeviceItemDto,
  PlaybackScanItemDto,
  PlaybackStatusItemDto,
  ScannedDeviceDto,
  DeviceUpsertDto,
} from '../dto/deviceDto'
import type { PaginatedDto } from '../dto/common'
import type {
  Device,
  DeviceStatusInfo,
  DeviceTestData,
  PlaybackDevice,
  ScannedDevice,
  ScannedDeviceDisplayItem,
  DeviceIdentifierField,
} from '../../domain/model/device'
import type { Paginated } from '../../domain/model/common'
import { toPaginated, toArrayOrPaginated } from './commonAdapter'
import { DeviceStatus } from '../../domain/enums'

// ===== 创建/更新：camelCase Domain → snake_case DTO =====

/**
 * 将 Domain Device（camelCase）转换为创建/更新请求体（snake_case）。
 *
 * create / update 两个 API 共用此函数，避免 20 字段映射重复书写。
 */
export function toDeviceUpsertDto(data: Partial<Device>): DeviceUpsertDto {
  return {
    name: data.name,
    model: data.model,
    type: data.type,
    system: data.system,
    system_version: data.systemVersion,
    app_name: data.appName,
    app_version: data.appVersion,
    description: data.description,
    location: data.location,
    max_audio_duration: data.maxAudioDuration,
    needs_prompt_audio: data.needsPromptAudio,
    prompt_config: data.promptConfig,
    connection_type: data.connectionType,
    keywords: data.keywords,
    serial_number: data.serialNumber,
    ip: data.ip,
    status: data.status,
    supported_algorithms: data.supportedAlgorithms,
  }
}

// ===== 通用：兜底归一（唯一允许做 snake_case 别名兼容的地方） =====

/**
 * 兜底归一 ScannedDevice —— 统一 serial / systemVersion 字段（后端别名兼容）。
 *
 * 后端 /test-devices/serials、/playback-devices/scan、/playback-devices、/test-devices
 * 等接口的原始 payload 别名不统一（serial ↔ serial_number、
 * system_version ↔ version ↔ os_version、system ↔ platform），
 * 在此处统一归一为 ScannedDevice 的 camelCase 字段。
 */
export function normalizeScannedDevice(dto: ScannedDeviceDto | null | undefined): ScannedDevice {
  if (!dto) return {}
  return {
    serial: dto.serial ?? dto.serial_number ?? dto.device_id ?? dto.device_unique_id,
    model: dto.model,
    system: dto.system ?? dto.platform,
    systemVersion: dto.system_version ?? dto.version ?? dto.os_version,
    name: dto.name,
    id: dto.id != null ? String(dto.id) : undefined,
    deviceUniqueId: dto.device_unique_id ?? dto.device_id,
    sampleRate: dto.sample_rate,
    channelIndex: dto.channel_index,
  }
}

/** 列表兜底归一 */
export function normalizeScannedDeviceList(dtos: ScannedDeviceDto[] | null | undefined): ScannedDevice[] {
  return (dtos ?? []).map(normalizeScannedDevice)
}

// ===== 测试设备 =====

/** DeviceItemDto → Device（逐字段显式映射，可选缺失用 ?.） */
export function toDevice(dto: DeviceItemDto): Device {
  return {
    id: dto?.id ?? '',
    name: dto?.name ?? '',
    model: dto?.model,
    description: dto?.description,
    type: dto?.type,
    system: dto?.system,
    systemVersion: dto?.system_version,
    appName: dto?.app_name,
    appVersion: dto?.app_version,
    location: dto?.location,
    maxAudioDuration: dto?.max_audio_duration,
    needsPromptAudio: dto?.needs_prompt_audio,
    promptConfig: dto?.prompt_config,
    connectionType: dto?.connection_type,
    keywords: dto?.keywords,
    serialNumber: dto?.serial_number,
    ip: dto?.ip,
    status: dto?.status,
    lastOnlineAt: dto?.last_online_at,
    createdAt: dto?.created_at,
    updatedAt: dto?.updated_at,
    driverName: dto?.driver_name,
    supportedAlgorithms: dto?.supported_algorithms,
  }
}

/** 设备分页列表 → Domain 分页 */
export function toDevicePage(dto: PaginatedDto<DeviceItemDto> | null | undefined): Paginated<Device> {
  return toPaginated(dto ?? { items: [], total: 0, page: 1, per_page: 0, pages: 1 }, toDevice)
}

/** 设备数组兜底（后端个别场景直接返回数组） */
export function toDeviceList(dto: PaginatedDto<DeviceItemDto> | DeviceItemDto[] | null | undefined): Device[] {
  return toArrayOrPaginated(dto, toDevice)
}

/** DeviceStatusItemDto → DeviceStatusInfo */
export function toDeviceStatusInfo(dto: DeviceStatusItemDto): DeviceStatusInfo {
  return {
    id: dto?.id ?? '',
    name: dto?.name ?? '',
    status: dto?.status,
    lastOnlineAt: dto?.last_online_at,
    model: dto?.model,
    system: dto?.system,
  }
}

/** 状态列表（get_statuses / health_check 共用） */
export function toDeviceStatusList(dtos: DeviceStatusItemDto[] | null | undefined): DeviceStatusInfo[] {
  return (dtos ?? []).map(toDeviceStatusInfo)
}

/** DeviceScanItemDto → ScannedDevice */
export function toScannedDevice(dto: DeviceScanItemDto): ScannedDevice {
  return {
    serial: dto?.serial,
    model: dto?.model,
    system: dto?.system,
    status: dto?.status,
    isRegistered: dto?.is_registered,
    id: dto?.id,
    name: dto?.name,
    type: dto?.type,
    systemVersion: dto?.system_version,
    appName: dto?.app_name,
    appVersion: dto?.app_version,
    ip: dto?.ip,
  }
}

/** 扫描结果列表 */
export function toScannedDeviceList(dtos: DeviceScanItemDto[] | null | undefined): ScannedDevice[] {
  return (dtos ?? []).map(toScannedDevice)
}

/** DeviceTestDataDto → DeviceTestData */
export function toDeviceTestData(dto: DeviceTestDataDto): DeviceTestData {
  return {
    id: dto?.id ?? '',
    status: dto?.status ?? DeviceStatus.OFFLINE,
    wakeupCommand: dto?.wakeup_command,
  }
}

// ===== 播放设备 =====

/** PlaybackDeviceItemDto → PlaybackDevice（逐字段显式映射） */
export function toPlaybackDevice(dto: PlaybackDeviceItemDto): PlaybackDevice {
  return {
    id: dto?.id ?? '',
    name: dto?.name ?? '',
    model: dto?.model,
    type: (dto?.device_type ?? 'dry') as PlaybackDevice['type'],
    deviceType: dto?.device_type,
    sampleRate: dto?.sample_rate,
    channelIndex: dto?.channel_index,
    deviceUniqueId: dto?.device_unique_id,
    description: dto?.description,
    status: dto?.status ?? DeviceStatus.OFFLINE,
    currentSplMappingId: dto?.current_spl_mapping_id,
    createdAt: dto?.created_at,
    updatedAt: dto?.updated_at,
  }
}

/** 播放设备分页列表 → Domain 分页 */
export function toPlaybackDevicePage(
  dto: PaginatedDto<PlaybackDeviceItemDto> | null | undefined
): Paginated<PlaybackDevice> {
  return toPaginated(dto ?? { items: [], total: 0, page: 1, per_page: 0, pages: 1 }, toPlaybackDevice)
}

/** 播放设备数组兜底 */
export function toPlaybackDeviceList(
  dto: PaginatedDto<PlaybackDeviceItemDto> | PlaybackDeviceItemDto[] | null | undefined
): PlaybackDevice[] {
  return toArrayOrPaginated(dto, toPlaybackDevice)
}

/** PlaybackScanItemDto → ScannedDevice（扫描结果复用 ScannedDevice 结构） */
export function toPlaybackScannedDevice(dto: PlaybackScanItemDto): ScannedDevice {
  return {
    name: dto?.name,
    model: dto?.model,
    serial: dto?.device_unique_id,
    deviceUniqueId: dto?.device_unique_id,
    type: dto?.type,
    system: undefined,
    status: dto?.status,
    sampleRate: dto?.sample_rate,
    channelIndex: dto?.channel_index,
  }
}

/** 播放设备扫描结果列表 */
export function toPlaybackScannedDeviceList(dtos: PlaybackScanItemDto[] | null | undefined): ScannedDevice[] {
  return (dtos ?? []).map(toPlaybackScannedDevice)
}

/** PlaybackStatusItemDto → DeviceStatusInfo（check_status 用） */
export function toPlaybackStatusInfo(dto: PlaybackStatusItemDto): DeviceStatusInfo {
  return {
    id: dto?.id ?? '',
    name: dto?.name ?? '',
    status: dto?.status,
  }
}

/** 播放设备状态列表 */
export function toPlaybackStatusList(dtos: PlaybackStatusItemDto[] | null | undefined): DeviceStatusInfo[] {
  return (dtos ?? []).map(toPlaybackStatusInfo)
}

// ===== INT-80 设备分组/操作/监控告警转换 =====

import type {
  DeviceGroupItemDto,
  DeviceGroupListDto,
  DeviceGroupUpsertDto,
  DeviceStatusEventDto,
  DeviceStatusHistoryDto,
  DeviceAlarmRuleDto,
  DeviceAlarmRuleListDto,
  DeviceAlarmRuleUpsertDto,
  DeviceAlarmDto,
  DeviceAlarmListDto,
} from '../dto/deviceDto'
import type {
  DeviceGroup,
  DeviceStatusEvent,
  DeviceAlarmRule,
  DeviceAlarm,
  DeviceBatchActionResult,
  AlarmMetricType,
} from '../../domain/model/device'

/** DeviceGroupItemDto → DeviceGroup */
export function toDeviceGroup(dto: DeviceGroupItemDto): DeviceGroup {
  return {
    id: dto?.id ?? '',
    name: dto?.name ?? '',
    description: dto?.description ?? '',
    groupType: dto?.group_type ?? 'test',
    deviceCount: dto?.device_count ?? 0,
    deviceIds: dto?.device_ids,
    createdAt: dto?.created_at,
    updatedAt: dto?.updated_at,
  }
}

/** 设备分组分页 → Paginated<DeviceGroup> */
export function toDeviceGroupPage(dto: DeviceGroupListDto | null | undefined): Paginated<DeviceGroup> {
  return toPaginated(dto, toDeviceGroup)
}

/** camelCase Domain 分组 → snake_case 请求体 */
export function toDeviceGroupUpsertDto(data: Partial<DeviceGroup>): DeviceGroupUpsertDto {
  const dto: DeviceGroupUpsertDto = {}
  if (data.name !== undefined) dto.name = data.name
  if (data.description !== undefined) dto.description = data.description
  if (data.groupType !== undefined) dto.group_type = data.groupType
  if (data.deviceIds !== undefined) dto.device_ids = data.deviceIds
  return dto
}

/** DeviceStatusEventDto → DeviceStatusEvent */
export function toDeviceStatusEvent(dto: DeviceStatusEventDto): DeviceStatusEvent {
  return {
    id: dto?.id ?? '',
    deviceId: dto?.device_id ?? '',
    eventType: dto?.event_type,
    fromStatus: dto?.from_status,
    toStatus: dto?.to_status,
    source: dto?.source,
    success: dto?.success,
    detail: dto?.detail,
    createdAt: dto?.created_at,
  }
}

/** 状态历史分页 → Paginated<DeviceStatusEvent> */
export function toDeviceStatusHistoryPage(
  dto: DeviceStatusHistoryDto | null | undefined
): Paginated<DeviceStatusEvent> {
  return toPaginated(dto, toDeviceStatusEvent)
}

/** DeviceAlarmRuleDto → DeviceAlarmRule */
export function toDeviceAlarmRule(dto: DeviceAlarmRuleDto): DeviceAlarmRule {
  return {
    id: dto?.id ?? '',
    name: dto?.name ?? '',
    metricType: (dto?.metric_type ?? 'offline_duration') as AlarmMetricType,
    thresholdValue: dto?.threshold_value ?? 0,
    severity: dto?.severity,
    notifyEmail: dto?.notify_email,
    enabled: dto?.enabled,
    createdAt: dto?.created_at,
    updatedAt: dto?.updated_at,
  }
}

/** 告警规则分页 → Paginated<DeviceAlarmRule> */
export function toDeviceAlarmRulePage(
  dto: DeviceAlarmRuleListDto | null | undefined
): Paginated<DeviceAlarmRule> {
  return toPaginated(dto, toDeviceAlarmRule)
}

/** camelCase 域规则 → snake_case 请求体 */
export function toDeviceAlarmRuleUpsertDto(data: Partial<DeviceAlarmRule>): DeviceAlarmRuleUpsertDto {
  const dto: DeviceAlarmRuleUpsertDto = {}
  if (data.name !== undefined) dto.name = data.name
  if (data.metricType !== undefined) dto.metric_type = data.metricType
  if (data.thresholdValue !== undefined) dto.threshold_value = data.thresholdValue
  if (data.severity !== undefined) dto.severity = data.severity
  if (data.notifyEmail !== undefined) dto.notify_email = data.notifyEmail
  if (data.enabled !== undefined) dto.enabled = data.enabled
  return dto
}

/** DeviceAlarmDto → DeviceAlarm */
export function toDeviceAlarm(dto: DeviceAlarmDto): DeviceAlarm {
  return {
    id: dto?.id ?? '',
    ruleId: dto?.rule_id,
    ruleName: dto?.rule_name,
    deviceId: dto?.device_id ?? '',
    deviceName: dto?.device_name,
    metricType: dto?.metric_type as AlarmMetricType | undefined,
    severity: dto?.severity,
    status: dto?.status,
    triggerValue: dto?.trigger_value,
    thresholdValue: dto?.threshold_value,
    content: dto?.content,
    emailSent: dto?.email_sent,
    emailError: dto?.email_error,
    triggeredAt: dto?.triggered_at,
    acknowledgedAt: dto?.acknowledged_at,
    acknowledgedBy: dto?.acknowledged_by,
    resolvedAt: dto?.resolved_at,
  }
}

/** 告警分页（含 stats）→ { items, total, stats } */
export function toDeviceAlarmPage(
  dto: DeviceAlarmListDto | null | undefined
): { items: DeviceAlarm[]; total: number; stats: DeviceAlarmListDto['stats'] } {
  const items = (dto?.items ?? []).map(toDeviceAlarm)
  return { items, total: dto?.total ?? items.length, stats: dto?.stats }
}

/** 批量操作响应 DTO → Domain */
export function toDeviceBatchActionResult(dto: unknown): DeviceBatchActionResult {
  const shape = (dto ?? {}) as {
    action?: string
    total?: number
    success_count?: number
    results?: { id: number | string; success?: boolean; message?: string }[]
    idempotent_replay?: boolean
  }
  return {
    action: shape.action,
    total: shape.total,
    successCount: shape.success_count,
    results: shape.results,
    idempotentReplay: shape.idempotent_replay,
  }
}

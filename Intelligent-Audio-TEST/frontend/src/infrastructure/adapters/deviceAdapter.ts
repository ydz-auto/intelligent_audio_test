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

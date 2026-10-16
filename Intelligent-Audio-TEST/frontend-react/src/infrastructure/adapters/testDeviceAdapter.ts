/**
 * 测试设备 DTO→Domain 适配器（infrastructure/adapters 层；16_设备域.md §10）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；Presentation 层不感知 snake_case。
 * 五态状态机值直接透传（在线/离线/连接中/断开中/错误），「测试中」占用态走 occupied。
 */
import type {
  DeviceFiveState,
  TestDevice,
} from '@/domain/models/testDevice'
import type { TestDeviceItemDto } from '@/infrastructure/dto/test-device.dto'

const FIVE_STATE_SET: ReadonlySet<string> = new Set([
  'online',
  'offline',
  'connecting',
  'disconnecting',
  'error',
])

export function toDeviceFiveState(status: string | null): DeviceFiveState | null {
  if (!status || !FIVE_STATE_SET.has(status)) return null
  return status as DeviceFiveState
}

export function testDeviceFromDto(dto: TestDeviceItemDto): TestDevice {
  return {
    id: dto.id,
    name: dto.name,
    model: dto.model,
    description: dto.description,
    type: dto.type,
    system: dto.system,
    systemVersion: dto.system_version,
    appName: dto.app_name,
    appVersion: dto.app_version,
    connectionType: dto.connection_type,
    serialNumber: dto.serial_number,
    ip: dto.ip,
    status: toDeviceFiveState(dto.status),
    lastOnlineAt: dto.last_online_at,
    driverName: dto.driver_name,
    supportedAlgorithms: dto.supported_algorithms,
    needsPromptAudio: dto.needs_prompt_audio,
    maxAudioDuration: dto.max_audio_duration,
    location: dto.location,
    keywords: dto.keywords,
    labId: dto.lab_id,
    labName: dto.lab_name,
    occupied: dto.occupied,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

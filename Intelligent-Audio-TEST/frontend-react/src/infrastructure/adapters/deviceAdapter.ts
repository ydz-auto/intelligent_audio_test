/**
 * 设备 DTO→Domain 适配器（infrastructure/adapters 层；10_测试执行.md §9）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；Presentation 层不感知 snake_case。
 * 现 Vue deviceAdapter.ts 平移。
 */
import { toDeviceType } from '@/domain/models/device'
import type { Device, DeviceStatus } from '@/domain/models/device'
import type { DeviceItemDto } from '@/infrastructure/dto/device.dto'

export function toDeviceStatus(status: string | null): DeviceStatus | null {
  if (!status) return null
  return status === 'online' ? 'online' : 'offline'
}

export function deviceFromDto(dto: DeviceItemDto): Device {
  return {
    id: dto.id,
    name: dto.name,
    model: dto.model,
    description: dto.description,
    type: toDeviceType(dto.type),
    system: dto.system,
    systemVersion: dto.system_version,
    serialNumber: dto.serial_number,
    ip: dto.ip,
    status: toDeviceStatus(dto.status),
    lastOnlineAt: dto.last_online_at,
    supportedAlgorithms: dto.supported_algorithms,
    connectionType: dto.connection_type,
    labId: dto.lab_id,
    labName: dto.lab_name,
  }
}

/**
 * 实验室 DTO→Domain 适配器（infrastructure/adapters 层；16_设备域.md §6.26/INT-487）。
 * 消费 laboratory.dto.ts snake_case 类型，产出 domain 模型。
 */
import type { Laboratory } from '@/domain/models/laboratory'
import type { LaboratoryDto } from '@/infrastructure/dto/laboratory.dto'

export function laboratoryFromDto(dto: LaboratoryDto): Laboratory {
  return {
    id: dto.id,
    code: dto.code,
    name: dto.name,
    building: dto.building,
    floor: dto.floor,
    roomNumber: dto.room_number,
    description: dto.description,
    status: dto.status,
    deviceCount: dto.device_count,
    playbackDeviceCount: dto.playback_device_count,
    testCaseCount: dto.test_case_count,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

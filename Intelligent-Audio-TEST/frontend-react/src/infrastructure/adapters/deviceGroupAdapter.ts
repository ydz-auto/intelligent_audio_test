/**
 * 设备分组 DTO→Domain 适配器（infrastructure/adapters 层；16_设备域.md §6.3/INT-80）。
 * 消费 device-group.dto.ts snake_case 类型，产出 domain 模型；
 * 后端无嵌套分组（§11-5 嵌套为前端 UI 稿），children 恒空。
 */
import type { DeviceGroup } from '@/domain/models/deviceGroup'
import type { DeviceGroupItemDto } from '@/infrastructure/dto/device-group.dto'

export function deviceGroupFromDto(dto: DeviceGroupItemDto): DeviceGroup {
  return {
    // 后端 device_groups.id 为 UUID 字符串，保持字符串语义（Number(uuid) 恒 NaN，P1 返修）
    id: String(dto.id),
    name: dto.name,
    description: dto.description ?? null,
    groupType: dto.group_type === 'playback' ? 'playback' : 'test',
    members: dto.device_ids ?? [],
    // P2-1：列表 device_ids 恒空，成员数以后端 device_count 为准（详情接口才含真实 device_ids）
    memberCount: dto.device_count ?? (dto.device_ids ?? []).length,
    children: [],
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

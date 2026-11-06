/**
 * 设备分组 DTO→Domain 适配器（infrastructure/adapters 层；16_设备域.md §6.3/INT-80）。
 * 消费 device-group.dto.ts snake_case 类型，产出 domain 模型。
 * INT-864（承接 INT-832）：后端 device_groups 增加 parent_id（可空），
 * deviceGroupFromDto 映射 parentId；deviceGroupsToTree 按 parentId 建嵌套树（children）。
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
    parentId: dto.parent_id != null ? String(dto.parent_id) : null,
    members: dto.device_ids ?? [],
    // P2-1：列表 device_ids 恒空，成员数以后端 device_count 为准（详情接口才含真实 device_ids）
    memberCount: dto.device_count ?? (dto.device_ids ?? []).length,
    children: [],
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

/**
 * 扁平分组列表 → 嵌套树（INT-832 契约：GET /test-devices/device-groups 扁平分页，
 * 每项含 parent_id，树由前端按 parentId 建）。
 * - parentId 为 null / 父分组不在列表（分页截断或脏数据）的项归为根。
 * - 不改变数组顺序（保持后端排序），仅按父子关系挂载 children。
 */
export function deviceGroupsToTree(groups: DeviceGroup[]): DeviceGroup[] {
  const byId = new Map<string, DeviceGroup>()
  for (const group of groups) byId.set(group.id, group)

  const roots: DeviceGroup[] = []
  for (const group of groups) {
    if (group.parentId != null) {
      const parent = byId.get(group.parentId)
      if (parent) {
        parent.children.push(group)
        continue
      }
    }
    roots.push(group)
  }
  return roots
}

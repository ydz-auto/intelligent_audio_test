/**
 * 设备分组 DTO（infrastructure/dto 层——snake_case 唯一出现层；16_设备域.md §6.3/INT-80）。
 * 形态对照 device_service device_group_repository.list_groups 实测：
 * id 后端为 str（Optional[str]）、device_ids 成员集合、无嵌套（children 前端空置）。
 */
import type { DeviceGroupType } from '@/domain/models/deviceGroup'

/** GET /test-devices/device-groups 列表项（DeviceGroupEntity.to_dict + device_count 装饰） */
export interface DeviceGroupItemDto {
  id: string | number
  name: string
  description: string | null
  group_type: DeviceGroupType | null
  created_by_user_id: number | null
  updated_by_user_id: number | null
  created_at: string | null
  updated_at: string | null
  device_ids: number[] | null
}

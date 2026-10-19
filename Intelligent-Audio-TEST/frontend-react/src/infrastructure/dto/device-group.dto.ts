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
  /** 列表接口恒空（P2-1 实测：后端列表 device_ids 为空，详情接口才返回真实成员） */
  device_ids: number[] | null
  /** 真实成员数（列表接口装饰字段；INT-721 P2-1 补） */
  device_count?: number | null
}

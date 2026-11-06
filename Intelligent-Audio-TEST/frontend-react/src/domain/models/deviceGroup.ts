/**
 * 设备分组领域模型（domain 层；16_设备域.md §6.3/INT-80 落位）。
 * 形态对照 device.py DeviceGroupCreateSchema + DeviceGroupMembersRequest 实测。
 * 嵌套分组（设备管理功能设计文档.md:214）、复制「{name}（副本）」（:248）、
 * 成员仅关联被测设备表（§11-5：播放设备组无成员落点，UI 禁用播放设备组）。
 * INT-864（承接 INT-832）：后端 device_groups 增加 parent_id（可空，根分组为 null），
 * 前端 infrastructure adapter 按 parent_id 建嵌套树（children）。
 */
/** 设备分组类型枚举（shared/models/common_enums.py DeviceGroupType：TEST/PLAYBACK） */
export type DeviceGroupType = 'test' | 'playback'

export const DEVICE_GROUP_TYPE_META: Record<
  DeviceGroupType,
  { label: string }
> = {
  test: { label: '测试设备组' },
  playback: { label: '播放设备组' },
}

export interface DeviceGroup {
  /** 分组 id：后端 device_groups.id 为 UUID 字符串（device_group.py id: Optional[str]） */
  id: string
  name: string
  description: string | null
  groupType: DeviceGroupType
  /** 父分组 id（INT-832；根分组为 null）。children 由 adapter 按 parent_id 建树 */
  parentId: string | null
  /** 成员设备 id（DeviceGroupMember 仅关联被测设备表）。
   *  注意：列表接口（GET /test-devices/device-groups）device_ids 恒空，
   *  真实成员以详情接口（GET /test-devices/device-groups/{id}）为准，按需拉取。 */
  members: number[]
  /** 真实成员数（列表接口 device_count 装饰；列表 device_ids 为空时以此为准显示） */
  memberCount: number
  /** 子分组（嵌套分组，:214；按后端 parent_id 建） */
  children: DeviceGroup[]
  createdAt: string | null
  updatedAt: string | null
}

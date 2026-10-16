/**
 * 设备分组领域模型（domain 层；16_设备域.md §6.3/INT-80 落位）。
 * 形态对照 device.py DeviceGroupCreateSchema + DeviceGroupMembersRequest 实测。
 * 嵌套分组（设备管理功能设计文档.md:214）、复制「{name}（副本）」（:248）、
 * 成员仅关联被测设备表（§11-5：播放设备组无成员落点，UI 禁用播放设备组）。
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
  id: number
  name: string
  description: string | null
  groupType: DeviceGroupType
  /** 成员设备 id（DeviceGroupMember 仅关联被测设备表） */
  members: number[]
  /** 子分组（嵌套分组，:214） */
  children: DeviceGroup[]
  createdAt: string | null
  updatedAt: string | null
}

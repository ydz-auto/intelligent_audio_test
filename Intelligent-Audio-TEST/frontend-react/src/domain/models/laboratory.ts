/**
 * 实验室领域模型（domain 层；16_设备域.md §6.26/INT-487 落位）。
 * 形态对照 doc/总架构/实验室扩展功能设计.md §4.1/§5.4.1：
 * id/code/name/building/floor/roomNumber/status/deviceCount/playbackDeviceCount/testCaseCount。
 * 后端 `/api/laboratories` CRUD 未实现（§11-24），mock 先行；入口禁用 + Tooltip 待后端立项。
 */
export type LaboratoryStatus = 'active' | 'inactive' | 'maintenance'

export const LABORATORY_STATUS_META: Record<
  LaboratoryStatus,
  { label: string; tone: 'success' | 'neutral' | 'warning' }
> = {
  active: { label: '启用', tone: 'success' },
  inactive: { label: '停用', tone: 'neutral' },
  maintenance: { label: '维护中', tone: 'warning' },
}

export interface Laboratory {
  id: number
  code: string
  name: string
  building: string | null
  floor: string | null
  roomNumber: string | null
  description: string | null
  status: LaboratoryStatus
  deviceCount: number
  playbackDeviceCount: number
  testCaseCount: number
  createdAt: string | null
  updatedAt: string | null
}

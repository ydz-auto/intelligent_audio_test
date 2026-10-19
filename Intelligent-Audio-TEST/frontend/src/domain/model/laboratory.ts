/**
 * Laboratory（实验室）领域模型 —— camelCase
 * 对应后端 api_gateway/schemas/laboratory.py::LaboratoryItem（INT-655）
 *
 * 设备/播放设备通过 lab_id 关联实验室，网关在列表 DTO 上装饰 lab_name；
 * 本模型用于「实验室」facet 选项与卡片「所属实验室」列展示。
 */

/** 实验室状态（后端 LaboratoryStatus 原值） */
export type LaboratoryStatusType = 'active' | 'inactive' | 'maintenance' | (string & {})

/** 实验室完整模型（对应 LaboratoryItem） */
export interface Laboratory {
  id: number
  /** 实验室代码（唯一，如 LAB-A-01） */
  code: string
  name: string
  building?: string
  floor?: string
  roomNumber?: string
  description?: string
  status?: LaboratoryStatusType
  /** 归属设备数 */
  deviceCount?: number
  /** 归属播放设备数 */
  playbackDeviceCount?: number
  /** 归属用例数 */
  testCaseCount?: number
  createdAt?: string
  updatedAt?: string
}

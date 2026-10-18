/**
 * Laboratory（实验室）DTO —— snake_case
 * 对应后端 api_gateway/schemas/laboratory.py::LaboratoryItem / LaboratoryListData（INT-655）
 */
import type { PaginatedDto } from './common'

/** 对应 LaboratoryItem（APIModel 序列化输出 snake_case） */
export interface LaboratoryItemDto {
  id: number
  code: string
  name: string
  building?: string
  floor?: string
  room_number?: string
  description?: string
  status?: string
  device_count?: number
  playback_device_count?: number
  test_case_count?: number
  created_at?: string
  updated_at?: string
}

/** 对应 LaboratoryListData（PaginatedData[LaboratoryItem]） */
export type LaboratoryListDto = PaginatedDto<LaboratoryItemDto>

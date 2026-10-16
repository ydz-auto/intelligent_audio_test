/**
 * 实验室 DTO（infrastructure/dto 层——snake_case 唯一出现层；16_设备域.md §6.26/INT-487）。
 * 数据契约按 doc/总架构/实验室扩展功能设计.md §5.1（GET/POST/PUT/DELETE /api/laboratories
 * + /{id}/summary）设计；后端 `/api/laboratories` CRUD 未实现（§11-24），mock 先行。
 */
import type { LaboratoryStatus } from '@/domain/models/laboratory'

/** /api/laboratories 列表项（实验室扩展功能设计.md §5.1/§5.4.1） */
export interface LaboratoryDto {
  id: number
  code: string
  name: string
  building: string | null
  floor: string | null
  room_number: string | null
  description: string | null
  status: LaboratoryStatus
  device_count: number
  playback_device_count: number
  test_case_count: number
  created_at: string | null
  updated_at: string | null
}

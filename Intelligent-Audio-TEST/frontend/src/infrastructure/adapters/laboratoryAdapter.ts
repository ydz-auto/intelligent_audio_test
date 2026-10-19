/**
 * Laboratory Adapter —— DTO(snake_case) → Domain(camelCase)
 *
 * 后端契约：api_gateway/schemas/laboratory.py::LaboratoryItem（INT-655）。
 * 本文件是 laboratory 相关接口唯一允许做 snake_case → camelCase 键名转换的地方。
 * ReadModel 定义在 domain/model/laboratory.ts，本文件只做转换。
 */
import type { LaboratoryItemDto, LaboratoryListDto } from '../dto/laboratoryDto'
import type { PaginatedDto } from '../dto/common'
import type { Laboratory } from '../../domain/model/laboratory'
import type { Paginated } from '../../domain/model/common'
import { toPaginated } from './commonAdapter'

/** LaboratoryItemDto → Laboratory（逐字段显式映射，可选缺失用 ?.） */
export function toLaboratory(dto: LaboratoryItemDto): Laboratory {
  return {
    id: dto?.id ?? 0,
    code: dto?.code ?? '',
    name: dto?.name ?? '',
    building: dto?.building,
    floor: dto?.floor,
    roomNumber: dto?.room_number,
    description: dto?.description,
    status: dto?.status,
    deviceCount: dto?.device_count,
    playbackDeviceCount: dto?.playback_device_count,
    testCaseCount: dto?.test_case_count,
    createdAt: dto?.created_at,
    updatedAt: dto?.updated_at,
  }
}

/** 实验室分页列表 → Domain 分页 */
export function toLaboratoryPage(dto: PaginatedDto<LaboratoryItemDto> | null | undefined): Paginated<Laboratory> {
  return toPaginated(dto ?? { items: [], total: 0, page: 1, per_page: 0, pages: 1 }, toLaboratory)
}

/** 实验室数组兜底（后端个别场景直接返回数组） */
export function toLaboratoryList(dto: LaboratoryListDto | LaboratoryItemDto[] | null | undefined): Laboratory[] {
  const items = Array.isArray(dto) ? dto : (dto?.items ?? [])
  return (items ?? []).map(toLaboratory)
}

/**
 * 分页 Adapter —— PaginatedDto → Paginated
 */
import type { Paginated } from '../../domain/model/common'
import type { PaginatedDto } from '../dto'

/** 将分页 DTO 中每个 item 经 itemAdapter 转换后组装为 Domain 分页结构 */
export function toPaginated<TDto, TDomain>(
  dto: PaginatedDto<TDto> | null | undefined,
  itemAdapter: (raw: TDto) => TDomain
): Paginated<TDomain> {
  if (!dto) {
    return { items: [], total: 0, page: 1, perPage: 0, pages: 1 }
  }
  return {
    items: (dto.items || []).map(itemAdapter),
    total: dto.total ?? dto.items?.length ?? 0,
    page: dto.page ?? 1,
    perPage: dto.per_page ?? dto.items?.length ?? 0,
    pages: dto.pages ?? 1,
  }
}

/** 安全数值（NaN / Infinity 回退默认值） */
export function toSafeNumber(value: unknown, fallback = 0): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

/** 数组响应兜底：后端部分接口直接返回数组而非分页对象 */
export function toArrayOrPaginated<TDto, TDomain>(
  data: PaginatedDto<TDto> | TDto[] | null | undefined,
  itemAdapter: (raw: TDto) => TDomain
): TDomain[] {
  if (!data) return []
  if (Array.isArray(data)) return data.map(itemAdapter)
  return (data.items || []).map(itemAdapter)
}

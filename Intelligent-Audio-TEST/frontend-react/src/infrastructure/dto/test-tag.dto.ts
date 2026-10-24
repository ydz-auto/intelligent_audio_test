/**
 * 标签/分类 DTO（infrastructure/dto 层——snake_case 唯一出现层；11_用例域.md §4.2 + INT-487）。
 * 形态对照 api_gateway/schemas/testcase.py TagCategoryItem / TagItem /
 * TagCategoryListData / TagDetailListData 实测逐字段。
 * 分类色/标签色均为业务数据自带的 color（数据驱动色，非主题色）。
 */
import type {
  TagCategory,
  TagCategoryDraft,
  TagDraft,
  TagItem,
} from '@/domain/models/testTag'

/** GET /tags/categories 分类项（testcase.py TagCategoryItem；null 字段后端省略） */
export interface TagCategoryDto {
  id: number
  name: string
  description?: string | null
  color?: string | null
  sort_order: number
  tag_count: number
  created_at?: string | null
  updated_at?: string | null
}

/** GET /tags/categories 列表响应（testcase.py TagCategoryListData） */
export interface TagCategoryListDataDto {
  items: TagCategoryDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** GET /tags 标签项（testcase.py TagItem；null 字段后端省略） */
export interface TagItemDto {
  id: number
  name: string
  description?: string | null
  color?: string | null
  category_id?: number | null
  category_name?: string | null
  created_at?: string | null
  updated_at?: string | null
}

/** GET /tags 列表响应（testcase.py TagDetailListData） */
export interface TagDetailListDataDto {
  items: TagItemDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/**
 * GET /tags/names 标签名列表响应（testcase.py TagListData；items 为纯名称字符串，
 * 供用例表单标签 Combobox 建议下拉按 keyword 服务端搜索，INT-1591 §5.1）
 */
export interface TagNameListDataDto {
  items: string[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** 分类创建/更新请求体（testcase.py TagCategoryCreate/UpdateSchema；null 字段省略） */
export interface TagCategoryUpsertDto {
  name?: string
  description?: string | null
  color?: string | null
  sort_order?: number
}

/** 标签创建/更新请求体（testcase.py TagCreate/UpdateSchema；null 字段省略） */
export interface TagUpsertDto {
  name?: string
  description?: string | null
  color?: string | null
  category_id?: number | null
}

/** TagCategoryDto → Domain TagCategory（显式逐字段映射；后端省略 null 字段时兜底 null） */
export function toTagCategory(dto: TagCategoryDto): TagCategory {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? null,
    color: dto.color ?? null,
    sortOrder: dto.sort_order,
    tagCount: dto.tag_count,
    createdAt: dto.created_at ?? null,
    updatedAt: dto.updated_at ?? null,
  }
}

/** TagItemDto → Domain TagItem（显式逐字段映射；后端省略 null 字段时兜底 null） */
export function toTagItem(dto: TagItemDto): TagItem {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? null,
    color: dto.color ?? null,
    categoryId: dto.category_id ?? null,
    categoryName: dto.category_name ?? null,
    createdAt: dto.created_at ?? null,
    updatedAt: dto.updated_at ?? null,
  }
}

/** Domain TagCategoryDraft → 请求体（snake_case；空值省略，后端 schema 字段可空） */
export function toTagCategoryUpsertDto(draft: TagCategoryDraft): TagCategoryUpsertDto {
  const dto: TagCategoryUpsertDto = { name: draft.name }
  if (draft.description !== undefined && draft.description !== null) {
    dto.description = draft.description
  }
  if (draft.color !== undefined && draft.color !== null) {
    dto.color = draft.color
  }
  if (draft.sortOrder !== undefined) {
    dto.sort_order = draft.sortOrder
  }
  return dto
}

/** Domain TagDraft → 请求体（snake_case；空值省略，后端 schema 字段可空） */
export function toTagUpsertDto(draft: TagDraft): TagUpsertDto {
  const dto: TagUpsertDto = { name: draft.name }
  if (draft.description !== undefined && draft.description !== null) {
    dto.description = draft.description
  }
  if (draft.color !== undefined && draft.color !== null) {
    dto.color = draft.color
  }
  if (draft.categoryId !== undefined && draft.categoryId !== null) {
    dto.category_id = draft.categoryId
  }
  return dto
}

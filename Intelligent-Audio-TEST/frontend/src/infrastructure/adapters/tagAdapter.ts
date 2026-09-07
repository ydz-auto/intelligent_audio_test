/**
 * Tag Adapter —— TagDto(snake_case) → Tag Domain(camelCase)
 *
 * 出口契约：domain/model/tag.ts；请求体转换在同文件下半部分。
 */
import type {
  Tag,
  TagItem,
  TagCategory,
  TagCategoryDraft,
  TagDraft,
} from '../../domain/model/tag'
import type {
  TagCategoryDto,
  TagCategoryListDto,
  TagItemDto,
  TagListDto,
  TagNameListDto,
  TagsByCategoryListDto,
  TagCategoryUpsertDto,
  TagUpsertDto,
  TagBatchCategoryDto,
} from '../dto/tagDto'

// ===== DTO → Domain =====

/** TagCategoryDto → TagCategory（显式逐字段映射） */
export function toTagCategory(dto: TagCategoryDto): TagCategory {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? undefined,
    color: dto.color ?? undefined,
    sortOrder: dto.sort_order ?? 0,
    tagCount: dto.tag_count ?? 0,
    createdAt: dto.created_at ?? undefined,
    updatedAt: dto.updated_at ?? undefined,
  }
}

/** TagItemDto → TagItem（显式逐字段映射） */
export function toTagItem(dto: TagItemDto): TagItem {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? undefined,
    color: dto.color ?? undefined,
    categoryId: dto.category_id ?? undefined,
    categoryName: dto.category_name ?? undefined,
    createdAt: dto.created_at ?? undefined,
    updatedAt: dto.updated_at ?? undefined,
  }
}

/** 兼容别名：Tag 与 TagItem 结构一致 */
export function toTag(dto: TagItemDto): Tag {
  return toTagItem(dto)
}

/** 分类列表 → TagCategoryList */
export function toTagCategoryList(dto: TagCategoryListDto | null | undefined) {
  return {
    items: (dto?.items ?? []).map(toTagCategory),
    total: dto?.total ?? 0,
  }
}

/** 标签列表 → TagList */
export function toTagList(dto: TagListDto | null | undefined) {
  return {
    items: (dto?.items ?? []).map(toTagItem),
    total: dto?.total ?? 0,
  }
}

/** 标签名列表 → TagNameList（值直通，无需字段转换） */
export function toTagNameList(dto: TagNameListDto | null | undefined) {
  return {
    items: dto?.items ?? [],
    total: dto?.total ?? 0,
  }
}

/** 按分类分组的标签列表 → TagsByCategoryList */
export function toTagsByCategoryList(dto: TagsByCategoryListDto | null | undefined) {
  return {
    items: (dto?.items ?? []).map(item => ({
      category: item.category ? toTagCategory(item.category) : null,
      tags: (item.tags ?? []).map(toTagItem),
    })),
    total: dto?.total ?? 0,
  }
}

// ===== Domain → DTO（请求体/查询参数） =====

/** 分类创建/更新请求体：TagCategoryDraft → TagCategoryUpsertDto */
export function toTagCategoryUpsertDto(draft: TagCategoryDraft): TagCategoryUpsertDto {
  return {
    name: draft.name,
    description: draft.description,
    color: draft.color,
    sort_order: draft.sortOrder,
  }
}

/** 标签创建/更新请求体：TagDraft → TagUpsertDto */
export function toTagUpsertDto(draft: TagDraft): TagUpsertDto {
  return {
    name: draft.name,
    description: draft.description,
    color: draft.color,
    category_id: draft.categoryId,
  }
}

/** 批量移动分类请求体（入参已为原始值，仅组装 snake_case 键） */
export function toTagBatchCategoryDto(tagIds: number[], categoryId: number | null): TagBatchCategoryDto {
  return {
    tag_ids: tagIds,
    category_id: categoryId,
  }
}

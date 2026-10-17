/**
 * 标签 API（infrastructure/api 层；接线 INT-648，经统一 client.ts）。
 * 对照后端 api_gateway/routes/tag_bp.py + schemas/testcase.py：
 *   GET  /tags/categories?page&per_page            （TagCategoryListData）
 *   POST /tags/categories                          （TagCategoryCreateSchema）
 *   PUT  /tags/categories/{id}                     （TagCategoryUpdateSchema）
 *   DELETE /tags/categories/{id}
 *   GET  /tags?page&per_page                       （TagDetailListData）
 *   POST /tags                                    （TagCreateSchema）
 *   PUT  /tags/{id}                               （TagUpdateSchema）
 *   DELETE /tags/{id}?cascade=false
 * 行内标签 Badge 依 TagItem.categoryName 分组着色、分类色走 TagItem.color（数据驱动色）。
 * snake→camel 转换收敛在 dto；application/domain 层只见 camelCase Domain。
 */
import { apiClient } from './client'
import type {
  TagCategory,
  TagCategoryDraft,
  TagDraft,
  TagItem,
} from '@/domain/models/testTag'
import {
  toTagCategory,
  toTagCategoryUpsertDto,
  toTagItem,
  toTagUpsertDto,
  type TagCategoryDto,
  type TagCategoryListDataDto,
  type TagDetailListDataDto,
  type TagItemDto,
} from '@/infrastructure/dto/test-tag.dto'

/** 标签/分类全量（facet 选项 + 登记表；现接口无分页 UI），拉大页供前端切分 */
const TAG_LIST_PAGE_SIZE = 100

/** 标签全量（名称→分类/色值映射登记表；用例行 TagCell 与标签 facet 共用） */
export async function fetchTags(): Promise<TagItem[]> {
  const dto = await apiClient.get<TagDetailListDataDto>('/tags', {
    params: { page: 1, per_page: TAG_LIST_PAGE_SIZE },
  })
  return (dto.items ?? []).map(toTagItem)
}

/** 标签分类（标签 facet 选项分组头 + 标签管理页左分类树） */
export async function fetchTagCategories(): Promise<TagCategory[]> {
  const dto = await apiClient.get<TagCategoryListDataDto>('/tags/categories', {
    params: { page: 1, per_page: TAG_LIST_PAGE_SIZE },
  })
  return (dto.items ?? []).map(toTagCategory)
}

/** 创建标签（POST /tags；TagCreateSchema → TagItem） */
export async function createTag(draft: TagDraft): Promise<TagItem> {
  const dto = await apiClient.post<TagItemDto>('/tags', toTagUpsertDto(draft))
  return toTagItem(dto)
}

/** 更新标签（PUT /tags/{id}；TagUpdateSchema → TagItem） */
export async function updateTag(
  id: number,
  draft: TagDraft
): Promise<TagItem> {
  const dto = await apiClient.put<TagItemDto>(
    `/tags/${id}`,
    toTagUpsertDto(draft)
  )
  return toTagItem(dto)
}

/** 删除标签（DELETE /tags/{id}?cascade=false；软删不级联） */
export async function deleteTag(id: number): Promise<void> {
  await apiClient.delete(`/tags/${id}`, {
    params: { cascade: false },
  })
}

/** 创建标签分类（POST /tags/categories；TagCategoryCreateSchema → TagCategory） */
export async function createCategory(
  draft: TagCategoryDraft
): Promise<TagCategory> {
  const dto = await apiClient.post<TagCategoryDto>(
    '/tags/categories',
    toTagCategoryUpsertDto(draft)
  )
  return toTagCategory(dto)
}

/** 更新标签分类（PUT /tags/categories/{id}；TagCategoryUpdateSchema → TagCategory） */
export async function updateCategory(
  id: number,
  draft: TagCategoryDraft
): Promise<TagCategory> {
  const dto = await apiClient.put<TagCategoryDto>(
    `/tags/categories/${id}`,
    toTagCategoryUpsertDto(draft)
  )
  return toTagCategory(dto)
}

/** 删除标签分类（DELETE /tags/categories/{id}；空分类才可删） */
export async function deleteCategory(id: number): Promise<void> {
  await apiClient.delete(`/tags/categories/${id}`)
}

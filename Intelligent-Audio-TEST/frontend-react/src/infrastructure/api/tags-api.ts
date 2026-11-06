/**
 * 标签 API（infrastructure/api 层；接线 INT-648，经统一 client.ts）。
 * 对照后端 api_gateway/routes/tag_bp.py + schemas/testcase.py：
 *   GET  /tags/categories?page&per_page            （TagCategoryListData）
 *   POST /tags/categories                          （TagCategoryCreateSchema）
 *   PUT  /tags/categories/{id}                     （TagCategoryUpdateSchema）
 *   DELETE /tags/categories/{id}
 *   GET  /tags?page&per_page                       （TagDetailListData）
 *   GET  /tags/names?page&per_page&keyword         （TagNameListData，标签名列表）
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
  TagCategoryGroup,
  TagDraft,
  TagItem,
} from '@/domain/models/testTag'
import {
  toTagCategory,
  toTagCategoryGroup,
  toTagCategoryUpsertDto,
  toTagItem,
  toTagUpsertDto,
  type TagByCategoryListDataDto,
  type TagCategoryDto,
  type TagCategoryListDataDto,
  type TagDetailListDataDto,
  type TagItemDto,
  type TagNameListDataDto,
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

/** 标签按分类分组（GET /tags/by-category；INT-487 口径——报告筛选 taxonomy 阶梯② 兜底数据源，
 *  返回分类→标签组，category=null 组即「未分类」） */
export async function fetchTagsByCategory(): Promise<TagCategoryGroup[]> {
  const dto = await apiClient.get<TagByCategoryListDataDto>('/tags/by-category')
  return (dto.items ?? []).map(toTagCategoryGroup)
}

/**
 * 标签名列表（GET /tags/names；keyword 服务端过滤）——用例表单标签 Combobox 建议下拉
 * 与「已有标签」搜索共用（11_用例域.md §5.1 / §4.3 `['tags','names']`，INT-1591）。
 */
export async function fetchTagNames(keyword?: string): Promise<string[]> {
  const dto = await apiClient.get<TagNameListDataDto>('/tags/names', {
    params: {
      page: 1,
      per_page: TAG_LIST_PAGE_SIZE,
      keyword: keyword?.trim() || undefined,
    },
  })
  return dto.items ?? []
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

/** 删除标签（DELETE /tags/{id}?cascade；cascade=true 级联软删标签下用例，对齐 11_用例域.md §3.6
 *  级联确认；标签管理页保持 cascade=false 软删不级联口径） */
export async function deleteTag(id: number, cascade = false): Promise<void> {
  await apiClient.delete(`/tags/${id}`, {
    params: { cascade },
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

/**
 * 标签 API（infrastructure/api 层；接线 INT-639，经统一 client.ts）。
 * 对照后端 api_gateway/routes/tag_bp.py + schemas/testcase.py：
 *   GET /api/v1/tags/categories?page=1&per_page=100   （TagCategoryListData）
 *   GET /api/v1/tags?page=1&per_page=100              （TagDetailListData）
 * 行内标签 Badge 依 TagItem.categoryName 分组着色、分类色走 TagItem.color（数据驱动色）。
 * snake→camel 转换收敛在 dto；application/domain 层只见 camelCase Domain。
 */
import { apiClient } from './client'
import type { TagCategory, TagItem } from '@/domain/models/testTag'
import {
  toTagCategory,
  toTagItem,
  type TagCategoryListDataDto,
  type TagDetailListDataDto,
} from '@/infrastructure/dto/test-tag.dto'

/** 标签全量/分类全量（facet 选项 + 登记表；现接口无分页 UI），拉大页供全量渲染 */
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

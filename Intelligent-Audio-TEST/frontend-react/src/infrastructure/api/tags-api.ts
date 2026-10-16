/**
 * 标签 API 桩（infrastructure 层，11_用例域.md §3.4 标签 facet 按分类呈现 + INT-487）。
 * 全部返回 mock 常量（红线④），接线时替换为真实请求：
 *   GET /api/v1/tags/categories           （testcase.py TagCategoryListData）
 *   GET /api/v1/tags?category_id&keyword  （TagDetailListData）
 *   GET /api/v1/tags/by-category          （INT-487：标签选项按分类分组）
 *   GET /api/v1/tags/names                （TagListData，名称串）
 * 行内标签 Badge 依 TagItem.categoryName 分组着色、分类色走 TagItem.color（数据驱动色）。
 */
import type { TagCategory, TagItem } from '@/domain/models/testTag'
import { MOCK_TAGS, MOCK_TAG_CATEGORIES } from '../mock/testcases-mock'

/** 模拟网络延迟（视觉稿演示用；接线后删除） */
function mockLatency<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), 120))
}

/** 标签全量（名称→分类/色值映射登记表；用例行 TagCell 与标签 facet 共用） */
export async function fetchTags(): Promise<TagItem[]> {
  // TODO(API 接线): GET /api/v1/tags?per_page=100
  return mockLatency(MOCK_TAGS)
}

/** 标签分类（标签 facet 选项分组头 = categoryName） */
export async function fetchTagCategories(): Promise<TagCategory[]> {
  // TODO(API 接线): GET /api/v1/tags/categories?per_page=100
  return mockLatency(MOCK_TAG_CATEGORIES)
}

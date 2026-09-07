/**
 * Tag（标签）DTO —— snake_case
 * 对应后端 api_gateway/schemas/testcase.py::TagItem / TagCategoryItem /
 * TagCategoryListData / TagDetailListData / TagListData
 */

/** 对应后端 TagCategoryItem */
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

/** 对应后端 TagCategoryListData */
export interface TagCategoryListDto {
  items: TagCategoryDto[]
  total: number
}

/** 对应后端 TagItem */
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

/** 对应后端 TagDetailListData */
export interface TagListDto {
  items: TagItemDto[]
  total: number
}

/** 对应后端 TagListData（标签名列表） */
export interface TagNameListDto {
  items: string[]
  total: number
}

/** 对应后端 /tags/by-category 的 items 元素（微服务返回 snake_case 字典） */
export interface TagsByCategoryItemDto {
  category: TagCategoryDto | null
  tags: TagItemDto[]
}

/** 对应后端 /tags/by-category 的 data */
export interface TagsByCategoryListDto {
  items: TagsByCategoryItemDto[]
  total: number
}

// ===== 请求体/查询参数（snake_case） =====

/** 对应后端 TagCategoryCreateSchema / TagCategoryUpdateSchema */
export interface TagCategoryUpsertDto {
  name?: string
  description?: string | null
  color?: string | null
  sort_order?: number
}

/** 对应后端 TagCreateSchema / TagUpdateSchema */
export interface TagUpsertDto {
  name?: string
  description?: string | null
  color?: string | null
  category_id?: number | null
}

/** 对应后端 PUT /tags/batch-category 请求体 */
export interface TagBatchCategoryDto {
  tag_ids: number[]
  category_id: number | null
}

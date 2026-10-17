/**
 * 标签/分类领域模型（domain 层；11_用例域.md §4.2 标签管理 + INT-487 标签带分类）。
 * 形态对照 api_gateway/schemas/testcase.py TagCategoryItem / TagItem 实测：
 * - TagCategory{id,name,description,color,sort_order,tag_count,created_at,updated_at}
 * - TagItem{id,name,description,color,category_id,category_name,created_at,updated_at}
 * 分类色/标签色均为业务数据自带的 color 字段（数据驱动色，非主题色，§6 口径）。
 */

export interface TagCategory {
  id: number
  name: string
  description: string | null
  color: string | null
  sortOrder: number
  tagCount: number
  createdAt: string | null
  updatedAt: string | null
}

export interface TagItem {
  id: number
  name: string
  description: string | null
  color: string | null
  categoryId: number | null
  categoryName: string | null
  createdAt: string | null
  updatedAt: string | null
}

/** 标签分类创建/更新入参（Domain，camelCase；infrastructure 层转 snake_case 请求体） */
export interface TagCategoryDraft {
  name: string
  description?: string | null
  color?: string | null
  sortOrder?: number
}

/** 标签创建/更新入参（Domain，camelCase；infrastructure 层转 snake_case 请求体） */
export interface TagDraft {
  name: string
  description?: string | null
  color?: string | null
  categoryId?: number | null
}

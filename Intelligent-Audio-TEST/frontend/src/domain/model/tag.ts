/**
 * Tag 领域模型 —— camelCase
 * 对应后端 api_gateway/schemas/testcase.py::TagItem / TagCategoryItem
 *
 * 后端序列化输出为 snake_case（APIModel，serialize_by_alias=False），
 * Infrastructure 层 adapter 负责字段名转换，本层零后端依赖。
 */

/** 标签（对应后端 TagItem；同时作为列表/详情/创建/更新出口契约） */
export interface Tag {
  id: number
  name: string
  description?: string
  color?: string
  categoryId?: number
  categoryName?: string
  createdAt?: string
  updatedAt?: string
}

/** 标签分类（对应后端 TagCategoryItem） */
export interface TagCategory {
  id: number
  name: string
  description?: string
  color?: string
  sortOrder: number
  tagCount: number
  createdAt?: string
  updatedAt?: string
}

/** 标签详情项（对应后端 TagItem，与 Tag 结构一致；保留独立命名供消费方沿用） */
export interface TagItem {
  id: number
  name: string
  description?: string
  color?: string
  categoryId?: number
  categoryName?: string
  createdAt?: string
  updatedAt?: string
}

/** 标签分类列表（对应后端 TagCategoryListData：非分页结构，仅 items + total） */
export interface TagCategoryList {
  items: TagCategory[]
  total: number
}

/** 标签列表（对应后端 TagDetailListData） */
export interface TagList {
  items: TagItem[]
  total: number
}

/** 标签名列表（对应后端 TagListData：items 为字符串数组） */
export interface TagNameList {
  items: string[]
  total: number
}

/** 按分类分组的标签项（对应后端 /tags/by-category 的 items 元素） */
export interface TagsByCategoryItem {
  category: TagCategory | null
  tags: TagItem[]
}

/** 按分类分组的标签列表（对应后端 /tags/by-category 的 data） */
export interface TagsByCategoryList {
  items: TagsByCategoryItem[]
  total: number
}

/** 标签分类创建/更新入参（Domain，camelCase；adapter 转 snake_case） */
export interface TagCategoryDraft {
  name?: string
  description?: string
  color?: string
  sortOrder?: number
}

/** 标签创建/更新入参（Domain，camelCase；adapter 转 snake_case） */
export interface TagDraft {
  name?: string
  description?: string
  color?: string
  categoryId?: number | null
}

/** 标签列表查询入参（Domain，camelCase；adapter 转 snake_case query） */
export interface TagListQuery {
  page?: number
  perPage?: number
  keyword?: string
  categoryId?: number
}

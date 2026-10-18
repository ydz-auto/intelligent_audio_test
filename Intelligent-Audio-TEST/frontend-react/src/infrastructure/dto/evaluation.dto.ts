/**
 * 评估维度 DTO（infrastructure/dto 层；snake_case 与后端 api_gateway/schemas/evaluation.py 对齐）。
 * 展示层不感知 snake_case；字段映射统一在 adapters/evaluationAdapter.ts。
 */

/** 维度关联算法（associated_algorithms 列表项） */
export interface DimensionAlgorithmAssociationDto {
  algorithm_type: string
  is_default?: boolean
  weight?: number
}

/** 维度项（DimensionItem 实测；字段多为 Optional，逐字段宽松） */
export interface DimensionItemDto {
  id: number
  name: string
  description?: string | null
  keywords?: string | null
  dimension_type?: string | null
  parent_dimension_id?: number | null
  category_id?: number | null
  api_url?: string | null
  api_endpoints?: unknown[] | null
  api_settings?: Record<string, unknown> | string | null
  api_status?: string | null
  score_unit?: string | null
  type?: string | null
  result_type?: number | null
  result_min?: number | null
  result_max?: number | null
  decimal_places?: number | null
  weight?: number | null
  sort_order?: number | null
  estimated_exec_time?: number | null
  rule?: unknown | string | null
  required_inputs?: unknown[] | null
  output_fields?: unknown[] | null
  statistic_method?: string | null
  agg_denominator?: string | null
  exclude_rounds?: number[] | null
  associated_algorithms?: DimensionAlgorithmAssociationDto[] | null
  status?: boolean | null
  created_at?: string | null
  updated_at?: string | null
}

/** 维度列表（DimensionListData） */
export interface DimensionListDataDto {
  items: DimensionItemDto[]
  total?: number
}

/** 维度选项（GET /evaluation/dimensions/options → data.dimensions） */
export interface DimensionOptionsDataDto {
  dimensions: Array<{
    id: number
    name: string
    description?: string | null
    type?: string | null
    dimension_type?: string | null
    category_id?: number | null
    task_type_code?: string | null
    requires_audio?: boolean
  }>
}

/** 评估分类（CategoryItem） */
export interface CategoryItemDto {
  id: number
  name: string
  description?: string | null
  icon?: string | null
  created_at?: string | null
  updated_at?: string | null
}

/** 分类列表（CategoryListData） */
export interface CategoryListDataDto {
  items: CategoryItemDto[]
  total?: number
}

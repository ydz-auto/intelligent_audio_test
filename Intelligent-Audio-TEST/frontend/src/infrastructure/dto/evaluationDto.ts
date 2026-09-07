/**
 * Evaluation（评估维度）DTO —— snake_case
 * 对应后端 api_gateway/schemas/evaluation.py
 */

/** 对应 DimensionItem */
export interface DimensionItemDto {
  id: number | string
  name: string
  description?: string
  keywords?: string
  dimension_type?: string
  parent_dimension_id?: number
  task_type_code?: string
  category_id?: number
  api_url?: string
  api_endpoints?: Record<string, unknown>[]
  api_settings?: Record<string, unknown> | string
  api_status?: string
  type?: string
  result_type?: number
  result_min?: number
  result_max?: number
  decimal_places?: number
  weight?: number
  estimated_exec_time?: number
  rule?: Record<string, unknown> | string
  required_inputs?: unknown
  output_fields?: unknown[]
  statistic_method?: string
  associated_algorithms?: Record<string, unknown>[]
  status?: boolean
  created_at?: string
  updated_at?: string
}

/** 对应 DimensionListData（PaginatedData[DimensionItem]） */
export interface DimensionListDto {
  items: DimensionItemDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** 对应 CategoryItem */
export interface CategoryItemDto {
  id: number
  name: string
  description?: string
  icon?: string
  created_at?: string
  updated_at?: string
}

/** 对应 CategoryListData { items, total } */
export interface CategoryListDto {
  items: CategoryItemDto[]
  total: number
}

/** 对应 get_dimension_options 返回 { dimensions: [...] } */
export interface DimensionOptionsDto {
  dimensions: Record<string, unknown>[]
}

/** 对应 HealthCheckResultItem */
export interface HealthCheckResultItemDto {
  url: string
  status: string
  status_code?: number
  response_time?: string
  message?: string
  error?: string
}

/** 对应 DimensionHealthCheckData */
export interface DimensionHealthCheckDto {
  results: HealthCheckResultItemDto[]
  overall_status: string
}

/** 对应 ScoreData */
export interface ScoreDataDto {
  score: number
}

/** 对应 TaskReevaluateResult */
export interface TaskReevaluateResultDto {
  total_cases: number
  queued_cases: number
  reextracted_cases: number
  message: string
}

/** 对应 DimensionImportResult */
export interface DimensionImportResultDto {
  imported: number
  updated: number
}

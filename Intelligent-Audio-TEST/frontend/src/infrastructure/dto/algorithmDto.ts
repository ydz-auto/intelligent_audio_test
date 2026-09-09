/**
 * Algorithm（算法配置）DTO —— snake_case
 * 对应后端 api_gateway/schemas/algorithm.py 与
 * task_service/application/algorithm/algorithm_crud_service.py 的序列化输出
 */

/** 对应 AlgorithmDetailResponse（算法详情 / 列表项） */
export interface AlgorithmDefinitionDto {
  id: number
  type: string
  name: string
  group_id?: number
  group_name?: string
  category?: string
  description?: string
  status?: string
  icon?: string
  display_order: number
  device_params?: Record<string, unknown>[]
  api_params?: Record<string, unknown>[]
  case_params?: Record<string, unknown>[]
  /** 兼容字段：device_params 别名（微服务同时输出 params） */
  params?: Record<string, unknown>[]
  /** 参考参数（对应 AlgorithmDetailResponse.reference_params） */
  reference_params?: AlgorithmReferenceParamDto[]
  /** 参数映射（按 source 分组：device / api / evaluation） */
  mappings?: Record<string, Record<string, unknown>[]>
  associated_dimensions?: Record<string, unknown>[]
  dimension_relations?: Record<string, unknown>[]
  created_at?: string
  updated_at?: string
}

/** 对应 list_algorithms 返回 { data, total } */
export interface AlgorithmListDto {
  data: AlgorithmDefinitionDto[]
  total: number
}

/** 设备参数项（对应 AlgorithmDeviceParamItem 序列化） */
export interface AlgorithmDeviceParamDto {
  id: number
  algorithm_type: string
  param_code: string
  param_name?: string
  label?: string
  param_type: string
  direction?: string
  required?: boolean
  default_value?: unknown
  options_source?: string
  options_field?: string
  options_label_field?: string
  validation?: unknown
  help_text?: string
  ui_order?: number
  hidden?: boolean
}

/** API 参数项（结构与设备参数一致） */
export interface AlgorithmApiParamDto extends AlgorithmDeviceParamDto {}

/** 用例专属参数项（对应 CaseAlgorithmParam 序列化） */
export interface AlgorithmCaseParamDto {
  id: number
  algorithm_type: string
  param_code: string
  param_name?: string
  label?: string
  param_type?: string
  required?: boolean
  default_value?: unknown
  help_text?: string
  ui_order?: number
  hidden?: boolean
  scope?: string
  min_value?: number
  max_value?: number
  step?: number
  unit?: string
}

/** 对应 list_params / list_case_params 返回 { parameters, total } */
export interface AlgorithmParamListDto {
  parameters: Record<string, unknown>[]
  total: number
}

/** 参数映射项（对应 list_mappings 返回的 mappings 列表项） */
export interface ParamMappingDto {
  id: number
  algorithm_type: string
  source: string
  source_param: string
  source_direction: string
  dimension_id?: number
  dimension_name?: string
  target_param: string
  transform_type: string
}

/** 对应 list_mappings 返回 { mappings, total } */
export interface ParamMappingListDto {
  mappings: ParamMappingDto[]
  total: number
}

/** 对应 AlgorithmGroupItem */
export interface AlgorithmGroupDto {
  id: number
  name: string
  description?: string
  icon?: string
  display_order: number
  algorithm_count: number
  created_at?: string
  updated_at?: string
}

/** 对应 list_groups 返回 { data, total } */
export interface AlgorithmGroupListDto {
  data: AlgorithmGroupDto[]
  total: number
}

/** 对应 get_algorithm_options 返回 { algorithms: [...] } */
export interface AlgorithmOptionDto {
  value: string
  name: string
  group_id?: number
  group_name?: string
  icon?: string
}

/** 对应 get_algorithm_dimensions 返回 */
export interface AlgorithmDimensionsDto {
  dimensions: Array<{
    id: number
    dimension_id?: number
    name: string
    description?: string
    type?: string
    weight: number
    is_default: boolean
  }>
  dimension_ids: number[]
  default_dimension_id: number | null
  weights: Record<string, number>
}

/** 对应 get_dimension_params 返回 { params: [...] } */
export interface DimensionParamDto {
  id: number
  dimension_id: number
  code: string
  param_code: string
  name?: string
  param_name?: string
  label?: string
  field_type: string
  param_direction?: string
  field_path?: string
  agg_role?: string
  output_role?: string
  visible_in_report?: boolean
  required?: boolean
  default_value?: unknown
  help_text?: string
  ui_order?: number
}

/** 对应 get_dimension_params 返回 { params: [...] } */
export interface DimensionParamsResultDto {
  params: DimensionParamDto[]
}

/** 对应 get_form_schema 返回（后端该接口直接输出 camelCase 字段） */
export interface AlgorithmFormSchemaDto {
  algorithmType: string
  algorithmName: string
  category?: string
  description?: string
  groups: Record<string, unknown>[]
  fields: Record<string, unknown>[]
}

/** 对应 ReloadConfigResponse */
export interface ReloadConfigDto {
  success: boolean
  message: string
  reload_time?: string
}

/** 对应 import 返回 */
export interface AlgorithmImportResultDto {
  imported: string[]
}

/** 对应 bulk_delete 返回 */
export interface AlgorithmBulkDeleteResultDto {
  deleted_types: string[]
}

/** 对应 ReferenceParam（参考参数） */
export interface AlgorithmReferenceParamDto {
  id?: number
  code: string
  name: string
  type?: string
  help_text?: string
  algorithm_type?: string
  annotation_code?: string
  annotation_format?: string
  field_path?: string
  merge_mode?: string
}

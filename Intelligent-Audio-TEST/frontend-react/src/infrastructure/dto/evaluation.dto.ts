/**
 * 评估域 DTO（infrastructure/dto 层——snake_case 唯一出现层；11_用例域.md §3.4/§4.1）。
 * 形态对照 api_gateway/schemas/evaluation.py 实测逐字段：DimensionItem / CategoryItem /
 * DimensionListData / CategoryListData / DimensionHealthCheckData / ScoreData /
 * BatchActionInput / DimensionOptionsQuery；算法选项对照 algorithm_bp.py:165 契约。
 * 全部转换函数在本层完成 snake→camel，domain 层只见 camelCase。
 */
import type {
  Dimension,
  DimensionApiSettings,
  DimensionHealthCheckData,
  DimensionOutputField,
  DimensionRequiredInput,
  EvaluationCategory,
  EvaluationDimensionItem,
  HealthCheckResultItem,
} from '@/domain/models/evaluationDimension'

/** GET /evaluation/categories 列表项（evaluation.py CategoryItem；无 status 字段） */
export interface CategoryItemDto {
  id: number
  name: string
  description: string | null
  icon: string | null
  created_at: string | null
  updated_at: string | null
}

/** GET /evaluation/categories 分页信封（CategoryListData；INT-297 统一分页信封） */
export interface CategoryListDataDto {
  items: CategoryItemDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** GET /evaluation/dimensions 列表项（evaluation.py DimensionItem；rule/api_endpoints 等宽松结构原样透传） */
export interface DimensionItemDto {
  id: number
  name: string
  description: string | null
  keywords: string | null
  dimension_type: string | null
  parent_dimension_id: number | null
  task_type_code: string | null
  category_id: number | null
  api_url: string | null
  api_endpoints: Dimension['apiEndpoints'] | null
  api_settings: DimensionApiSettings | null
  api_status: string | null
  score_unit: string | null
  type: string | null
  result_type: number | null
  result_min: number | null
  result_max: number | null
  decimal_places: number | null
  weight: number | null
  sort_order: number | null
  estimated_exec_time: number | null
  rule: Dimension['rule'] | null
  required_inputs: Dimension['requiredInputs'] | null
  output_fields: Dimension['outputFields'] | null
  statistic_method: string | null
  agg_denominator: string | null
  exclude_rounds: number[] | null
  associated_algorithms: AlgorithmAssociationDto[] | null
  status: boolean | null
  created_at: string | null
  updated_at: string | null
}

/** 关联算法 wire 项（snake_case；adapter 归一为 AlgorithmAssociation） */
export interface AlgorithmAssociationDto {
  algorithm_type: string
  is_default: boolean
  weight: number | null
}

/** GET /evaluation/dimensions 分页信封（DimensionListData） */
export interface DimensionListDataDto {
  items: DimensionItemDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** GET /evaluation/dimensions/options 数据（DimensionOptionsData；facet 主维度子集） */
export interface DimensionOptionsDataDto {
  dimensions: Array<{
    id: number
    name: string
    algorithm_type?: string | null
    is_default?: boolean
    weight?: number
    description?: string | null
    /** 评估类型（auto/manual，domain 层 Dimension.type）；勿误当 dimensionType 用 */
    type?: string | null
    /** 主/子维度（main/sub；options 端点实测含此字段，INT-1030 审计打回修正 type 错读） */
    dimension_type?: string | null
  }>
}

/** GET /algorithm/options 数据（algorithm_bp.py:165；{ algorithms: [...] }） */
export interface AlgorithmOptionsDataDto {
  algorithms: Array<{
    value: string
    name: string
    group_id?: number | null
    group_name?: string | null
    icon?: string | null
  }>
}

/** POST /evaluation/dimensions/{id}/health 结果（DimensionHealthCheckData） */
export interface DimensionHealthCheckDataDto {
  results: Array<{
    url: string
    status: string
    status_code?: number | null
    response_time?: string | null
    message?: string | null
    error?: string | null
  }>
  overall_status: string
}

/** POST /evaluation/dimensions/{id}/calculate 结果（ScoreData） */
export interface ScoreDataDto {
  score: number
}

/** POST /evaluation/dimensions/batch 请求体（BatchActionInput；ids/action） */
export interface DimensionBatchActionDto {
  ids: Array<number | string>
  action: string
}

/** POST /evaluation/dimensions/reorder 请求体（ids 顺序即新展示顺序） */
export interface DimensionReorderDto {
  ids: Array<number | string>
}

// ===== DTO → Domain 适配（snake→camel 唯一转换层） =====

/** 嵌套列表归一：数组原样；字符串 JSON 解析为数组（旧数据兼容，照 adapter parseNestedList） */
function toNestedList(value: unknown): Record<string, unknown>[] | undefined {
  if (Array.isArray(value)) return value as Record<string, unknown>[]
  if (typeof value !== 'string' || !value.trim()) return undefined
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : undefined
  } catch {
    return undefined
  }
}

/**
 * required_inputs 归一（snake_case wire → camelCase domain；INT-1350 二轮：与写侧
 * toDimensionInputDto 的 param_code 口径同源，兼容旧数据 key/description 与双形态键）。
 */
function toDimensionRequiredInputs(value: unknown): DimensionRequiredInput[] | null {
  const list = toNestedList(value)
  if (!list) return null
  return list.map((item) => {
    const record = item as Record<string, unknown>
    return {
      id: (record.id as number) ?? null,
      dimensionId: (record.dimension_id ?? record.dimensionId) as number | null,
      paramCode: String(record.param_code ?? record.paramCode ?? record.key ?? ''),
      paramName: String(record.param_name ?? record.paramName ?? record.label ?? ''),
      label: String(record.label ?? record.param_name ?? record.paramName ?? ''),
      fieldType: String(record.field_type ?? record.fieldType ?? 'text'),
      required: record.required === undefined ? true : Boolean(record.required),
      defaultValue: record.default_value ?? record.defaultValue,
      helpText: record.help_text
        ? String(record.help_text)
        : record.description
          ? String(record.description)
          : undefined,
      uiOrder: (record.ui_order ?? record.uiOrder) as number | null,
    }
  })
}

/**
 * output_fields 归一（snake_case wire → camelCase domain；INT-1350 二轮：补齐
 * param_code 读取，否则编辑回显 paramCode 恒空、保存时清空已落库配置。兼容旧数据
 * name 键与双形态键）。
 */
function toDimensionOutputFields(value: unknown): DimensionOutputField[] | null {
  const list = toNestedList(value)
  if (!list) return null
  return list.map((item) => {
    const record = item as Record<string, unknown>
    return {
      id: (record.id as number) ?? null,
      dimensionId: (record.dimension_id ?? record.dimensionId) as number | null,
      paramCode: String(record.param_code ?? record.paramCode ?? record.name ?? ''),
      paramName: String(record.param_name ?? record.paramName ?? record.label ?? ''),
      label: String(record.label ?? record.param_name ?? record.paramName ?? ''),
      fieldPath: String(
        record.field_path ?? record.fieldPath ?? record.param_code ?? record.paramCode ?? ''
      ),
      fieldType: String(record.field_type ?? record.fieldType ?? 'number'),
      outputRole: String(record.output_role ?? record.outputRole ?? 'main'),
      aggRole: String(record.agg_role ?? record.aggRole ?? ''),
      defaultValue: record.default_value ?? record.defaultValue,
      visibleInReport:
        record.visible_in_report === undefined ? true : Boolean(record.visible_in_report),
      helpText: record.help_text ? String(record.help_text) : undefined,
      uiOrder: (record.ui_order ?? record.uiOrder) as number | null,
    }
  })
}

/** CategoryItemDto → EvaluationCategory */
export function toEvaluationCategory(dto: CategoryItemDto): EvaluationCategory {
  return {
    id: dto.id,
    name: dto.name ?? '',
    description: dto.description,
    icon: dto.icon,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

/** DimensionItemDto → Dimension（rule/api_settings/api_endpoints 宽松结构原样透传） */
export function toDimension(dto: DimensionItemDto): Dimension {
  return {
    id: dto.id,
    name: dto.name ?? '',
    description: dto.description,
    keywords: dto.keywords,
    dimensionType: (dto.dimension_type ?? 'main') as Dimension['dimensionType'],
    parentDimensionId: dto.parent_dimension_id,
    categoryId: dto.category_id,
    apiUrl: dto.api_url,
    apiEndpoints: dto.api_endpoints ?? undefined,
    apiSettings: dto.api_settings ?? undefined,
    apiStatus: dto.api_status,
    scoreUnit: dto.score_unit,
    type: dto.type,
    resultType: dto.result_type,
    resultMin: dto.result_min,
    resultMax: dto.result_max,
    decimalPlaces: dto.decimal_places,
    weight: dto.weight,
    sortOrder: dto.sort_order,
    estimatedExecTime: dto.estimated_exec_time,
    rule: dto.rule,
    // INT-1350 二轮：读侧归一 snake_case→camelCase，与写侧 toDimensionInputDto 同口径。
    // 此前原样透传 dto.required_inputs/output_fields（wire 为 snake_case），编辑回显
    // paramCode 恒空 → 保存时后端 _save_output_params 空 param_code 逐行 continue 且
    // 编辑先删后写 → 已落库输出字段/输入参数被清空。
    requiredInputs: toDimensionRequiredInputs(dto.required_inputs),
    outputFields: toDimensionOutputFields(dto.output_fields),
    statisticMethod: dto.statistic_method,
    aggDenominator: dto.agg_denominator,
    excludeRounds: dto.exclude_rounds,
    associatedAlgorithms: (dto.associated_algorithms ?? []).map((a) => ({
      algorithmType: a.algorithm_type,
      isDefault: Boolean(a.is_default),
      weight: a.weight ?? 1,
    })),
    status: dto.status,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

/** 维度选项数据 → EvaluationDimensionItem[]（facet singleSelect 子集） */
export function toDimensionOptionsList(
  dto: DimensionOptionsDataDto | null | undefined
): EvaluationDimensionItem[] {
  return (dto?.dimensions ?? []).map((item) => ({
    id: item.id,
    name: item.name ?? '',
    description: item.description ?? null,
    // INT-1030 审计打回：item.type 是评估类型（auto/manual），dimensionType 应取 dimension_type
    dimensionType: (item.dimension_type ?? 'main') as EvaluationDimensionItem['dimensionType'],
    parentDimensionId: null,
    categoryId: null,
    weight: item.weight ?? null,
    // INT-646 代码审计 P3-3：is_default 语义为「是否默认评估维度」，独立字段映射，
    // 不再错位映射为 status（启用状态）
    isDefault: item.is_default ?? null,
    status: null,
    createdAt: null,
    updatedAt: null,
  }))
}

/** 算法选项数据 → {value, label}[]（关联算法 facet/表单 Combobox 消费） */
export function toAlgorithmOptionsList(
  dto: AlgorithmOptionsDataDto | null | undefined
): Array<{ value: string; label: string }> {
  return (dto?.algorithms ?? []).map((item) => ({
    value: item.value ?? '',
    label: item.name ?? item.value ?? '',
  }))
}

/** DimensionHealthCheckDataDto → DimensionHealthCheckData */
export function toDimensionHealthCheck(
  dto: DimensionHealthCheckDataDto | null | undefined
): DimensionHealthCheckData {
  const results: HealthCheckResultItem[] = (dto?.results ?? []).map((item) => ({
    url: item.url ?? '',
    status: item.status ?? '',
    statusCode: item.status_code,
    responseTime: item.response_time,
    message: item.message,
    error: item.error,
  }))
  return {
    results,
    overallStatus: dto?.overall_status ?? 'unknown',
  }
}

// ===== Domain → snake_case 请求体（写侧转换） =====

/** Partial<Dimension>（camelCase）→ DimensionInput 请求体（snake_case；与 Vue toDimensionDto 口径一致） */
export function toDimensionInputDto(data: Partial<Dimension>): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  if (data.name !== undefined) result.name = data.name
  if (data.description !== undefined) result.description = data.description
  if (data.keywords !== undefined) result.keywords = data.keywords
  if (data.dimensionType !== undefined) result.dimension_type = data.dimensionType
  if (data.parentDimensionId !== undefined) result.parent_dimension_id = data.parentDimensionId
  if (data.categoryId !== undefined) result.category_id = data.categoryId
  if (data.apiUrl !== undefined) result.api_url = data.apiUrl
  if (data.apiEndpoints !== undefined) result.api_endpoints = data.apiEndpoints
  if (data.apiSettings !== undefined) result.api_settings = data.apiSettings
  if (data.apiStatus !== undefined) result.api_status = data.apiStatus
  if (data.scoreUnit !== undefined) result.score_unit = data.scoreUnit
  if (data.type !== undefined) result.type = data.type
  if (data.resultType !== undefined) result.result_type = data.resultType
  if (data.resultMin !== undefined) result.result_min = data.resultMin
  if (data.resultMax !== undefined) result.result_max = data.resultMax
  if (data.decimalPlaces !== undefined) result.decimal_places = data.decimalPlaces
  if (data.weight !== undefined) result.weight = data.weight
  if (data.sortOrder !== undefined) result.sort_order = data.sortOrder
  if (data.estimatedExecTime !== undefined) result.estimated_exec_time = data.estimatedExecTime
  if (data.rule !== undefined) result.rule = data.rule
  if (data.requiredInputs !== undefined) {
    const inputs = Array.isArray(data.requiredInputs) ? data.requiredInputs : []
    result.required_inputs = inputs.map((item) => ({
      key: item.paramCode,
      label: item.label,
      field_type: item.fieldType,
      required: item.required,
      default_value: item.defaultValue,
      description: item.helpText,
    }))
  }
  if (data.outputFields !== undefined) {
    const fields = Array.isArray(data.outputFields) ? data.outputFields : []
    result.output_fields = fields.map((item) => ({
      // INT-1350：后端 _save_output_params 只读 param_code（无 key/name 兜底），
      // 之前误映射为 name → param_code 恒空 → 输出字段静默丢弃。对齐 required_inputs
      // 的 param_code 口径，并补齐 _save_output_params 全部读取键。
      param_code: item.paramCode,
      param_name: item.paramName,
      label: item.label,
      field_path: item.fieldPath,
      field_type: item.fieldType,
      output_role: item.outputRole,
      agg_role: item.aggRole,
      default_value: item.defaultValue,
      visible_in_report: item.visibleInReport,
      help_text: item.helpText,
      ui_order: item.uiOrder,
    }))
  }
  if (data.statisticMethod !== undefined) result.statistic_method = data.statisticMethod
  if (data.aggDenominator !== undefined) result.agg_denominator = data.aggDenominator
  if (data.excludeRounds !== undefined) result.exclude_rounds = data.excludeRounds
  if (data.associatedAlgorithms !== undefined) result.associated_algorithms = data.associatedAlgorithms
  if (data.status !== undefined) result.status = data.status
  if (data.llmJudgeConfig !== undefined) result.llm_judge_config = data.llmJudgeConfig
  return result
}

/** Partial<EvaluationCategory>（camelCase）→ CategoryCreateInput/CategoryUpdateInput 请求体 */
export function toCategoryInputDto(data: Partial<EvaluationCategory>): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  if (data.name !== undefined) result.name = data.name
  if (data.description !== undefined) result.description = data.description
  if (data.icon !== undefined) result.icon = data.icon
  return result
}

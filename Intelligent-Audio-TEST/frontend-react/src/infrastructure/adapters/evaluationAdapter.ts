/**
 * 评估维度 DTO→Domain 适配器（infrastructure/adapters 层；11_用例域.md §10 契约）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；Presentation 层不感知 snake_case。
 * INT-714 接线 read 路径（音频导入上传选项/用例 facet 消费真实维度与算法选项）。
 */
import type {
  Dimension,
  DimensionApiEndpoint,
  DimensionApiSettings,
  DimensionOutputField,
  DimensionRequiredInput,
  DimensionRule,
  EvaluationCategory,
  EvaluationDimensionItem,
} from '@/domain/models/evaluationDimension'
import type {
  CategoryItemDto,
  DimensionItemDto,
} from '@/infrastructure/dto/evaluation.dto'

const MAIN_TYPE = new Set(['main'])

function toRule(value: unknown): DimensionRule | string | null {
  if (value === undefined || value === null) return null
  if (typeof value === 'string') return value
  return value as DimensionRule
}

/** 嵌套列表归一：数组原样；字符串 JSON 解析为数组（旧数据兼容，照 Vue parseNestedList） */
function parseNestedList(value: unknown): Record<string, unknown>[] | undefined {
  if (Array.isArray(value)) return value as Record<string, unknown>[]
  if (typeof value !== 'string' || !value.trim()) return undefined
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : undefined
  } catch {
    return undefined
  }
}

function toRequiredInputs(value: unknown): DimensionRequiredInput[] | null {
  const list = parseNestedList(value)
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

function toOutputFields(value: unknown): DimensionOutputField[] | null {
  const list = parseNestedList(value)
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

function toApiEndpoints(value: unknown[] | null | undefined): DimensionApiEndpoint[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => {
    const record = item as Record<string, unknown>
    return {
      url: String(record.url ?? ''),
      name: String(record.name ?? ''),
      priority: Number(record.priority ?? 1),
      maxProcess: Number(record.max_process ?? record.maxProcess ?? 5),
      maxTimeout: Number(record.max_timeout ?? record.maxTimeout ?? 30),
      maxAudioDuration: Number(record.max_audio_duration ?? record.maxAudioDuration ?? 60),
    }
  })
}

function toApiSettings(value: Record<string, unknown> | string | null | undefined): DimensionApiSettings | string | undefined {
  if (value === undefined || value === null) return undefined
  if (typeof value === 'string') return value
  return value as DimensionApiSettings
}

/** 维度项完整映射（DimensionItem → Dimension） */
export function dimensionFromDto(dto: DimensionItemDto): Dimension {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? null,
    keywords: dto.keywords ?? null,
    dimensionType: dto.dimension_type === 'main' || dto.dimension_type === 'sub'
      ? dto.dimension_type
      : null,
    parentDimensionId: dto.parent_dimension_id ?? null,
    categoryId: dto.category_id ?? null,
    apiUrl: dto.api_url ?? null,
    apiEndpoints: toApiEndpoints(dto.api_endpoints),
    apiSettings: toApiSettings(dto.api_settings),
    apiStatus: dto.api_status ?? null,
    scoreUnit: dto.score_unit ?? null,
    type: dto.type ?? null,
    resultType: dto.result_type ?? null,
    llmJudge: dto.llm_judge ?? false,
    resultMin: dto.result_min ?? null,
    resultMax: dto.result_max ?? null,
    decimalPlaces: dto.decimal_places ?? null,
    weight: dto.weight ?? null,
    sortOrder: dto.sort_order ?? null,
    estimatedExecTime: dto.estimated_exec_time ?? null,
    rule: toRule(dto.rule),
    requiredInputs: toRequiredInputs(dto.required_inputs),
    outputFields: toOutputFields(dto.output_fields),
    statisticMethod: dto.statistic_method ?? null,
    aggDenominator: dto.agg_denominator ?? null,
    excludeRounds: dto.exclude_rounds ?? null,
    associatedAlgorithms: dto.associated_algorithms?.map((a) => ({
      algorithmType: a.algorithm_type,
      isDefault: Boolean(a.is_default),
      weight: a.weight ?? 1,
    })) ?? null,
    status: dto.status ?? null,
    createdAt: dto.created_at ?? null,
    updatedAt: dto.updated_at ?? null,
  }
}

/** facet 子集（仅主维度；EvaluationDimensionItem 消费口径） */
export function dimensionOptionFromDto(
  dto: DimensionItemDto
): EvaluationDimensionItem {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? null,
    dimensionType: MAIN_TYPE.has(dto.dimension_type ?? '') ? 'main' : 'sub',
    parentDimensionId: dto.parent_dimension_id ?? null,
    categoryId: dto.category_id ?? null,
    weight: dto.weight ?? null,
    status: dto.status ?? null,
    createdAt: dto.created_at ?? null,
    updatedAt: dto.updated_at ?? null,
  }
}

/** 分类项映射（CategoryItem → EvaluationCategory） */
export function categoryFromDto(dto: CategoryItemDto): EvaluationCategory {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? null,
    icon: dto.icon ?? null,
    createdAt: dto.created_at ?? null,
    updatedAt: dto.updated_at ?? null,
  }
}

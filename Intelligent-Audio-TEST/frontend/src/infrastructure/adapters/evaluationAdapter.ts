/**
 * Evaluation Adapter —— DTO(snake_case) → Domain(camelCase)
 *
 * 后端契约：api_gateway/schemas/evaluation.py。
 * 本文件是 evaluation 相关接口唯一允许做 snake_case → camelCase 键名转换的地方。
 * ReadModel 定义在 domain/model/dimension.ts，本文件只做转换。
 */
import type {
  DimensionItemDto,
  DimensionListDto,
  CategoryItemDto,
  CategoryListDto,
  DimensionOptionsDto,
  DimensionHealthCheckDto,
  ScoreDataDto,
  TaskReevaluateResultDto,
  DimensionImportResultDto,
} from '../dto/evaluationDto'
import type {
  Dimension,
  EvaluationCategory,
  EvaluationCategoryList,
  DimensionOptionsResult,
  DimensionOption,
  TaskReevaluateResult,
} from '../../domain/model/dimension'
import type {
  DimensionHealthCheckResult,
} from '../../domain/model/evaluationTypes'
import type { Paginated } from '../../domain/model/common'
import { toPaginated } from './commonAdapter'
import { camelizeKeys } from '../../utils/keyTransform'

// ===== 评估维度 =====

/** 维度关联算法（后端 associated_algorithms 列表项 → AlgorithmAssociation） */
function toAssociation(raw: Record<string, unknown>): import('../../domain/model/dimension').AlgorithmAssociation {
  return {
    algorithmType: String(raw?.algorithm_type ?? raw?.algorithmType ?? ''),
    isDefault: Boolean(raw?.is_default ?? raw?.isDefault ?? false),
    weight: Number(raw?.weight ?? 1),
  }
}

/** DimensionItemDto → Dimension（逐字段显式映射，可选缺失用 ?.） */
export function toDimension(dto: DimensionItemDto): Dimension {
  return {
    id: dto?.id ?? '',
    name: dto?.name ?? '',
    description: dto?.description,
    keywords: dto?.keywords,
    dimensionType: (dto?.dimension_type ?? 'main') as Dimension['dimensionType'],
    parentDimensionId: dto?.parent_dimension_id ?? null,
    taskTypeCode: dto?.task_type_code,
    categoryId: dto?.category_id,
    apiUrl: dto?.api_url,
    apiEndpoints: dto?.api_endpoints as Dimension['apiEndpoints'],
    apiSettings: (dto?.api_settings ? camelizeKeys(dto.api_settings) : undefined) as Dimension['apiSettings'],
    apiStatus: dto?.api_status,
    type: dto?.type,
    resultType: dto?.result_type,
    resultMin: dto?.result_min,
    resultMax: dto?.result_max,
    decimalPlaces: dto?.decimal_places,
    weight: dto?.weight,
    estimatedExecTime: dto?.estimated_exec_time,
    rule: (dto?.rule ?? undefined) as Dimension['rule'],
    requiredInputs: dto?.required_inputs as string | undefined,
    outputFields: dto?.output_fields,
    statisticMethod: dto?.statistic_method,
    associatedAlgorithms: (dto?.associated_algorithms ?? []).map(toAssociation),
    status: dto?.status,
    createdAt: dto?.created_at,
    updatedAt: dto?.updated_at,
  }
}

/** 维度分页列表 → Domain 分页 */
export function toDimensionPage(dto: DimensionListDto | null | undefined): Paginated<Dimension> {
  return toPaginated(
    dto ?? { items: [], total: 0, page: 1, per_page: 0, pages: 1 },
    toDimension
  )
}

/** 维度数组兜底 */
export function toDimensionList(dtos: DimensionItemDto[] | null | undefined): Dimension[] {
  return (dtos ?? []).map(toDimension)
}

// ===== 分类 =====

/** CategoryItemDto → EvaluationCategory */
export function toEvaluationCategory(dto: CategoryItemDto): EvaluationCategory {
  return {
    id: dto?.id ?? 0,
    name: dto?.name ?? '',
    description: dto?.description,
    icon: dto?.icon,
    createdAt: dto?.created_at,
    updatedAt: dto?.updated_at,
  }
}

/** CategoryListDto → EvaluationCategoryList */
export function toEvaluationCategoryList(dto: CategoryListDto | null | undefined): EvaluationCategoryList {
  return {
    items: (dto?.items ?? []).map(toEvaluationCategory),
    total: dto?.total ?? 0,
  }
}

// ===== 维度选项 =====

/** DimensionOptionsDto → DimensionOptionsResult（逐字段显式映射） */
export function toDimensionOptions(dto: DimensionOptionsDto | null | undefined): DimensionOptionsResult {
  const rawItems = dto?.dimensions ?? []
  const items: DimensionOption[] = rawItems.map(raw => {
    const record = raw as Record<string, unknown>
    return {
      id: (record?.id ?? '') as number | string,
      name: String(record?.name ?? ''),
      algorithmType: record?.algorithm_type as string | undefined,
      isDefault: Boolean(record?.is_default ?? false),
      weight: Number(record?.weight ?? 1),
      description: typeof record?.description === 'string' ? record.description : undefined,
      type: typeof record?.type === 'string' ? record.type : undefined,
    }
  })
  return { dimensions: items }
}

// ===== 健康探测 / 计分 / 其他 =====

/** DimensionHealthCheckDto → DimensionHealthCheckResult */
export function toDimensionHealthCheck(dto: DimensionHealthCheckDto | null | undefined): DimensionHealthCheckResult {
  return {
    results: (dto?.results ?? []).map(item => ({
      url: item?.url ?? '',
      status: item?.status ?? '',
      statusCode: item?.status_code,
      responseTime: item?.response_time,
      message: item?.message,
      error: item?.error,
    })),
    overallStatus: dto?.overall_status ?? 'unknown',
  }
}

/** ScoreDataDto → score */
export function toScore(dto: ScoreDataDto | null | undefined): number {
  return dto?.score ?? 0
}

/** TaskReevaluateResultDto → TaskReevaluateResult */
export function toTaskReevaluateResult(dto: TaskReevaluateResultDto | null | undefined): TaskReevaluateResult {
  return {
    totalCases: dto?.total_cases ?? 0,
    queuedCases: dto?.queued_cases ?? 0,
    reextractedCases: dto?.reextracted_cases ?? 0,
    message: dto?.message ?? '',
  }
}

/** DimensionImportResultDto → { imported, updated } */
export function toDimensionImportResult(dto: DimensionImportResultDto | null | undefined): { imported: number; updated: number } {
  return {
    imported: dto?.imported ?? 0,
    updated: dto?.updated ?? 0,
  }
}

// ===== 提交方向转换：Domain → snake_case 请求体 =====

/** Dimension（camelCase）→ snake_case 请求体 DTO */
export function toDimensionDto(data: Partial<Dimension>): Record<string, any> {
  const result: Record<string, any> = {}
  if (data.id !== undefined) result.id = data.id
  if (data.name !== undefined) result.name = data.name
  if (data.description !== undefined) result.description = data.description
  if (data.keywords !== undefined) result.keywords = data.keywords
  if (data.dimensionType !== undefined) result.dimension_type = data.dimensionType
  if (data.parentDimensionId !== undefined) result.parent_dimension_id = data.parentDimensionId
  if (data.taskTypeCode !== undefined) result.task_type_code = data.taskTypeCode
  if (data.categoryId !== undefined) result.category_id = data.categoryId
  if (data.apiUrl !== undefined) result.api_url = data.apiUrl
  if (data.apiEndpoints !== undefined) result.api_endpoints = data.apiEndpoints
  if (data.apiSettings !== undefined) result.api_settings = data.apiSettings
  if (data.type !== undefined) result.type = data.type
  if (data.resultType !== undefined) result.result_type = data.resultType
  if (data.resultMin !== undefined) result.result_min = data.resultMin
  if (data.resultMax !== undefined) result.result_max = data.resultMax
  if (data.decimalPlaces !== undefined) result.decimal_places = data.decimalPlaces
  if (data.weight !== undefined) result.weight = data.weight
  if (data.estimatedExecTime !== undefined) result.estimated_exec_time = data.estimatedExecTime
  if (data.rule !== undefined) result.rule = data.rule
  if (data.requiredInputs !== undefined) result.required_inputs = data.requiredInputs
  if (data.outputFields !== undefined) result.output_fields = data.outputFields
  if (data.statisticMethod !== undefined) result.statistic_method = data.statisticMethod
  if (data.associatedAlgorithms !== undefined) result.associated_algorithms = data.associatedAlgorithms
  if (data.status !== undefined) result.status = data.status
  if (data.scoreUnit !== undefined) result.score_unit = data.scoreUnit
  if (data.llmJudgeConfig !== undefined) result.llm_judge_config = data.llmJudgeConfig
  return result
}

/** EvaluationCategory（camelCase）→ snake_case 请求体 DTO */
export function toCategoryDto(data: Partial<EvaluationCategory>): Record<string, any> {
  const result: Record<string, any> = {}
  if (data.id !== undefined) result.id = data.id
  if (data.name !== undefined) result.name = data.name
  if (data.description !== undefined) result.description = data.description
  if (data.icon !== undefined) result.icon = data.icon
  return result
}

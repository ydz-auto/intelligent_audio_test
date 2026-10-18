/**
 * 评估维度 API（infrastructure 层；11_用例域.md §3.4 facet + §4.1 评估维度页）。
 * INT-714 接线 read 路径（GET 族）+ INT-715 接线写路径（save/delete/batch/weight/
 * reorder/calculate/health/duplicate/category CRUD）——真实请求对照
 * api_gateway/schemas/evaluation.py + routes/evaluation_bp.py：
 *   GET  /api/v1/evaluation/dimensions/options?algorithm_type=…    （DimensionOptionsQuery；facet）
 *   GET  /api/v1/evaluation/dimensions?category_id&page&per_page&search （DimensionListData；INT-281 主/子同屏全量）
 *   GET  /api/v1/evaluation/categories                             （CategoryListData）
 *   GET  /api/v1/algorithm/options                                 （关联算法 facet/表单）
 *   POST/PUT /api/v1/evaluation/dimensions|/{id}                  （维度保存；dim_manage）
 *   DELETE /api/v1/evaluation/dimensions/{id}                     （维度删除）
 *   POST /api/v1/evaluation/dimensions/batch                       （批量启用/禁用/删除）
 *   PUT  /api/v1/evaluation/dimensions/{id}                        （权重滑杆 { weight }）
 *   POST /api/v1/evaluation/dimensions/reorder                     （ids 顺序即新展示序）
 *   POST /api/v1/evaluation/dimensions/{id}/calculate              （规则试算）
 *   GET  /api/v1/evaluation/dimensions/{id}/health                 （API 健康探测）
 *   POST/PUT/DELETE /api/v1/evaluation/categories|/{id}            （分类管理）
 * snake_case 契约只在 infrastructure/dto/evaluation.dto.ts 出现（read 侧 adapter 收敛），
 * 本层与 domain 只见 camelCase。
 */
import type {
  Dimension,
  DimensionHealthCheckData,
  EvaluationCategory,
  EvaluationDimensionItem,
  HealthCheckResultItem,
} from '@/domain/models/evaluationDimension'
import { apiClient } from './client'
import type {
  CategoryListDataDto,
  DimensionListDataDto,
  DimensionOptionsDataDto,
} from '@/infrastructure/dto/evaluation.dto'
import {
  categoryFromDto,
  dimensionFromDto,
} from '@/infrastructure/adapters/evaluationAdapter'

/** 写路径响应信封（POST/PUT/DELETE 统一 { success, code, message, data } → data） */
type WriteEnvelope = {
  success?: boolean
  code?: number
  message?: string
  data?: unknown
}

/** POST /evaluation/dimensions/{id}/calculate 响应（ScoreData） */
interface ScoreDataDto {
  score: number
}

/** GET /evaluation/dimensions/{id}/health 响应（DimensionHealthCheckData） */
interface DimensionHealthCheckDataDto {
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

/** 维度选项（facet singleSelect；GET /evaluation/dimensions/options，仅主维度） */
export async function fetchDimensionOptions(
  algorithmType?: string
): Promise<EvaluationDimensionItem[]> {
  const dto = await apiClient.get<DimensionOptionsDataDto>(
    '/evaluation/dimensions/options',
    { params: { algorithm_type: algorithmType } }
  )
  return (dto?.dimensions ?? [])
    .filter((d) => d.dimension_type !== 'sub')
    .map((d) => ({
      id: d.id,
      name: d.name,
      description: d.description ?? null,
      dimensionType: d.dimension_type === 'main' ? 'main' : 'sub',
      parentDimensionId: d.category_id ?? null,
      categoryId: d.category_id ?? null,
      weight: null,
      status: null,
      createdAt: null,
      updatedAt: null,
    }))
}

/** 评估维度全量（列表/分组双视图；GET /evaluation/dimensions?per_page=1000 主/子同屏；列表不下发 required_inputs/output_fields） */
export async function fetchEvaluationDimensions(): Promise<Dimension[]> {
  const dto = await apiClient.get<DimensionListDataDto>('/evaluation/dimensions', {
    params: { page: 1, per_page: 1000 },
  })
  return (dto?.items ?? []).map(dimensionFromDto)
}

/**
 * 维度详情（编辑用；GET /evaluation/dimensions/{id}）。
 * 列表接口不下发 required_inputs/output_fields（恒 []），编辑反填必须走详情
 * （对照 Vue openEditModal → evaluationPort.getOne(id) 口径）。
 */
export async function fetchEvaluationDimensionDetail(
  id: number | string
): Promise<Dimension> {
  const dto = await apiClient.get<DimensionItemDto>(`/evaluation/dimensions/${id}`)
  return dimensionFromDto(dto)
}

/** 评估分类（分类 facet + 分组视图组头；GET /evaluation/categories） */
export async function fetchEvaluationCategories(): Promise<EvaluationCategory[]> {
  const dto = await apiClient.get<CategoryListDataDto>('/evaluation/categories', {
    params: { page: 1, per_page: 100 },
  })
  return (dto?.items ?? []).map(categoryFromDto)
}

/** 算法选项（关联算法 facet singleSelect + 维度表单关联算法 Combobox；GET /algorithm/options） */
export async function fetchAlgorithmOptions(): Promise<
  Array<{ value: string; label: string }>
> {
  const dto = await apiClient.get<{ algorithms?: Array<{ value?: string; name?: string }> }>(
    '/algorithm/options'
  )
  return (dto?.algorithms ?? []).map((a) => ({
    value: a.value ?? '',
    label: a.name ?? a.value ?? '',
  }))
}

/** 维度保存请求体（Partial<Dimension> camelCase → DimensionInput snake_case；照 Vue toDimensionDto 口径） */
function toDimensionInputDto(data: Partial<Dimension>): Record<string, unknown> {
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
      param_code: item.paramCode,
      param_name: item.paramName || item.label,
      label: item.label || item.paramName,
      field_type: item.fieldType,
      required: item.required,
      default_value: item.defaultValue != null ? item.defaultValue : undefined,
      help_text: item.helpText || undefined,
      ui_order: item.uiOrder ?? undefined,
    }))
  }
  if (data.outputFields !== undefined) {
    const fields = Array.isArray(data.outputFields) ? data.outputFields : []
    result.output_fields = fields.map((item) => ({
      param_code: item.paramCode,
      param_name: item.paramName || item.label,
      label: item.label || item.paramName,
      field_path: item.fieldPath,
      field_type: item.fieldType,
      output_role: item.outputRole,
      agg_role: item.aggRole,
      default_value: item.defaultValue != null ? item.defaultValue : undefined,
      visible_in_report: item.visibleInReport,
      help_text: item.helpText || undefined,
      ui_order: item.uiOrder ?? undefined,
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

/** 保存维度（新增/编辑/权重更新共用；有 id 走 PUT /{id}，无 id 走 POST） */
export async function saveEvaluationDimension(
  input: Partial<Dimension>
): Promise<{ success: boolean }> {
  const body = toDimensionInputDto(input)
  if (input.id != null && input.id !== '' && !String(input.id).startsWith('copy-')) {
    await apiClient.put<WriteEnvelope>(`/evaluation/dimensions/${input.id}`, body)
  } else {
    await apiClient.post<WriteEnvelope>('/evaluation/dimensions', body)
  }
  return { success: true }
}

/** 删除维度（逻辑删除） */
export async function deleteEvaluationDimension(
  id: number | string
): Promise<{ success: boolean }> {
  await apiClient.delete<WriteEnvelope>(`/evaluation/dimensions/${id}`)
  return { success: true }
}

/** 批量操作（启用/禁用/删除；BatchActionInput { ids, action }） */
export async function batchEvaluationDimensions(
  ids: Array<number | string>,
  action: 'enable' | 'disable' | 'delete'
): Promise<{ success: boolean; updatedCount: number }> {
  await apiClient.post<WriteEnvelope>('/evaluation/dimensions/batch', { ids, action })
  return { success: true, updatedCount: ids.length }
}

/** 权重滑杆提交（拖动停止 onValueCommitted 才触发，§4.1/§10-4；PUT /{id} 载荷 { weight }） */
export async function updateDimensionWeight(
  id: number | string,
  weight: number
): Promise<{ success: boolean }> {
  await apiClient.put<WriteEnvelope>(`/evaluation/dimensions/${id}`, { weight })
  return { success: true }
}

/** 维度上移/下移（主维度整块移动、子维度仅同组内移动；POST /reorder 载荷 ids 顺序即新展示序） */
export async function reorderDimension(
  ids: Array<number | string>
): Promise<{ success: boolean }> {
  await apiClient.post<WriteEnvelope>('/evaluation/dimensions/reorder', { ids })
  return { success: true }
}

/** 规则试算（POST /evaluation/dimensions/{id}/calculate；后端回 score，命中规则行本地推导高亮） */
export async function calculateDimensionScore(
  dimension: Dimension,
  value: number
): Promise<{ score: number; matchedRule: { condition: string; value: number; score: number } | null }> {
  const dto = await apiClient.post<ScoreDataDto>(
    `/evaluation/dimensions/${dimension.id}/calculate`,
    { value }
  )
  const score = dto?.score ?? 0
  const rules = Array.isArray(dimension.rule)
    ? dimension.rule
    : typeof dimension.rule === 'object' && dimension.rule?.rules
      ? dimension.rule.rules
      : []
  let matchedRule: { condition: string; value: number; score: number } | null = null
  for (const rule of rules) {
    const { condition, value: threshold } = rule
    const hit =
      condition === '>=' ? value >= threshold :
      condition === '<=' ? value <= threshold :
      condition === '>' ? value > threshold :
      condition === '<' ? value < threshold :
      condition === '=' ? value === threshold : false
    if (hit) {
      matchedRule = rule
      break
    }
  }
  return { score, matchedRule }
}

/** 测试 API 健康（行内「测试 API」；GET /{id}/health，门槛 evaluation:read） */
export async function testDimensionHealth(
  dimension: Dimension
): Promise<DimensionHealthCheckData> {
  const dto = await apiClient.get<DimensionHealthCheckDataDto>(
    `/evaluation/dimensions/${dimension.id}/health`
  )
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

/** 复制维度（后端无独立 duplicate 端点：以「{原名}（副本）」为名 POST 创建，配置深拷贝） */
export async function duplicateDimension(
  dimension: Dimension
): Promise<{ success: boolean }> {
  const body = toDimensionInputDto({
    ...dimension,
    name: `${dimension.name}（副本）`,
  })
  await apiClient.post<WriteEnvelope>('/evaluation/dimensions', body)
  return { success: true }
}

/** 导入维度（POST /evaluation/dimensions/import；multipart：file + updateExisting；返回 { imported, updated }） */
export async function importEvaluationDimensions(
  file: File,
  updateExisting: boolean
): Promise<{ imported: number; updated: number }> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('updateExisting', updateExisting ? 'true' : 'false')
  const data = await apiClient.post<{
    imported?: number
    updated?: number
  }>('/evaluation/dimensions/import', formData)
  return { imported: data?.imported ?? 0, updated: data?.updated ?? 0 }
}

/** 导出维度（GET /evaluation/dimensions/export?format=json|excel → 维度数据数组，前端落盘） */
export async function exportEvaluationDimensions(
  format: 'json' | 'excel'
): Promise<Array<Record<string, unknown>>> {
  const dto = await apiClient.get<Array<Record<string, unknown>>>(
    '/evaluation/dimensions/export',
    { params: { format } }
  )
  return Array.isArray(dto) ? dto : []
}

/** 分类保存请求体（Partial<EvaluationCategory> camelCase → CategoryCreateInput/UpdateInput） */
function toCategoryInputDto(data: Partial<EvaluationCategory>): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  if (data.name !== undefined) result.name = data.name
  if (data.description !== undefined) result.description = data.description
  if (data.icon !== undefined) result.icon = data.icon
  return result
}

/** 保存分类（新增/编辑；有 id 走 PUT /categories/{id}，无 id 走 POST；门槛 category_manage） */
export async function saveEvaluationCategory(
  input: Partial<EvaluationCategory>
): Promise<{ success: boolean }> {
  const body = toCategoryInputDto(input)
  if (input.id != null) {
    await apiClient.put<WriteEnvelope>(`/evaluation/categories/${input.id}`, body)
  } else {
    await apiClient.post<WriteEnvelope>('/evaluation/categories', body)
  }
  return { success: true }
}

/** 删除分类（DELETE /evaluation/categories/{id}；门槛 category_manage） */
export async function deleteEvaluationCategory(
  id: number
): Promise<{ success: boolean }> {
  await apiClient.delete<WriteEnvelope>(`/evaluation/categories/${id}`)
  return { success: true }
}

/**
 * 评估维度 API（infrastructure/api 层；11_用例域.md §3.4 facet + §4.1 评估维度页）。
 * 已接线（INT-646）：全部经 client.ts 统一 fetch 封装走真实后端，端点对照
 * api_gateway/routes/evaluation_bp.py 实测：
 *   GET  /api/v1/evaluation/dimensions/options?algorithm_type=…  （DimensionOptionsData；facet）
 *   GET  /api/v1/evaluation/dimensions?category_id&page&per_page&search（DimensionListData）
 *   GET  /api/v1/evaluation/categories                            （CategoryListData）
 *   GET  /api/v1/algorithm/options                                 （算法 facet/表单）
 *   POST/PUT /api/v1/evaluation/dimensions|/{id}                  （维度保存；dim_manage）
 *   DELETE /api/v1/evaluation/dimensions/{id}                     （维度删除）
 *   POST /api/v1/evaluation/dimensions/batch                       （批量启用/禁用/删除）
 *   POST /api/v1/evaluation/dimensions/reorder                     （ids 顺序即新展示序）
 *   POST /api/v1/evaluation/dimensions/{id}/calculate              （规则试算）
 *   GET  /api/v1/evaluation/dimensions/{id}/health                 （API 健康探测）
 *   POST/PUT/DELETE /api/v1/evaluation/categories|/{id}            （分类管理）
 * snake_case 契约只在 infrastructure/dto/evaluation.dto.ts 出现，本层与 domain 只见 camelCase。
 */
import type {
  Dimension,
  DimensionHealthCheckData,
  EvaluationCategory,
} from '@/domain/models/evaluationDimension'
import { request } from '@/infrastructure/api/client'
import {
  type CategoryListDataDto,
  type DimensionHealthCheckDataDto,
  type DimensionListDataDto,
  type DimensionOptionsDataDto,
  type ScoreDataDto,
  toAlgorithmOptionsList,
  toCategoryInputDto,
  toDimension,
  toDimensionHealthCheck,
  toDimensionInputDto,
  toDimensionOptionsList,
  toEvaluationCategory,
} from '@/infrastructure/dto/evaluation.dto'
import type { EvaluationDimensionItem } from '@/domain/models/evaluationDimension'

/** 维度选项（facet singleSelect；仅主维度，子维度折叠进主维度 Popover 内滚动） */
export async function fetchDimensionOptions(
  algorithmType?: string
): Promise<EvaluationDimensionItem[]> {
  const dto = await request<DimensionOptionsDataDto>('GET', '/evaluation/dimensions/options', undefined, {
    params: { algorithm_type: algorithmType || '' },
  })
  return toDimensionOptionsList(dto)
}

/** 评估维度全量（列表/分组双视图；主/子同屏聚合，前端过滤分页；per_page=1000 全量拉取） */
export async function fetchEvaluationDimensions(): Promise<Dimension[]> {
  const dto = await request<DimensionListDataDto>('GET', '/evaluation/dimensions', undefined, {
    params: { per_page: 1000 },
  })
  return (dto?.items ?? []).map(toDimension)
}

/** 评估分类（分类 facet + 分组视图组头 + 分类表单） */
export async function fetchEvaluationCategories(): Promise<EvaluationCategory[]> {
  const dto = await request<CategoryListDataDto>('GET', '/evaluation/categories', undefined, {
    params: { per_page: 100 },
  })
  return (dto?.items ?? []).map(toEvaluationCategory)
}

/** 算法选项（关联算法 facet singleSelect + 维度表单关联算法 Combobox；algorithm:read） */
export async function fetchAlgorithmOptions(): Promise<
  Array<{ value: string; label: string }>
> {
  const dto = await request<{ algorithms: Array<{ value: string; name: string }> }>(
    'GET',
    '/algorithm/options'
  )
  return toAlgorithmOptionsList(dto)
}

/** 保存维度（新增/编辑/权重更新共用；有 id 走 PUT /{id}，无 id 走 POST） */
export async function saveEvaluationDimension(
  input: Partial<Dimension>
): Promise<{ success: boolean }> {
  const body = toDimensionInputDto(input)
  if (input.id != null && input.id !== '' && !String(input.id).startsWith('copy-')) {
    await request('PUT', `/evaluation/dimensions/${input.id}`, body)
  } else {
    await request('POST', '/evaluation/dimensions', body)
  }
  return { success: true }
}

/** 删除维度（逻辑删除） */
export async function deleteEvaluationDimension(
  id: number | string
): Promise<{ success: boolean }> {
  await request('DELETE', `/evaluation/dimensions/${id}`)
  return { success: true }
}

/** 批量操作（启用/禁用/删除；BatchActionInput） */
export async function batchEvaluationDimensions(
  ids: Array<number | string>,
  action: 'enable' | 'disable' | 'delete'
): Promise<{ success: boolean; updatedCount: number }> {
  await request('POST', '/evaluation/dimensions/batch', { ids, action })
  return { success: true, updatedCount: ids.length }
}

/** 权重滑杆提交（拖动停止 onValueCommitted 才触发，§4.1/§10-4；PUT /{id} 载荷 { weight }） */
export async function updateDimensionWeight(
  id: number | string,
  weight: number
): Promise<{ success: boolean }> {
  await request('PUT', `/evaluation/dimensions/${id}`, { weight })
  return { success: true }
}

/**
 * 维度上移/下移（主维度整块移动、子维度仅同组内移动）。
 * 后端 reorder 契约：ids 顺序即新展示顺序（下标即 sort_order）——调用方需传
 * 当前筛选集完整重排后的 id 序（Vue reorder(ids) 同口径）。
 */
export async function reorderDimension(
  ids: Array<number | string>
): Promise<{ success: boolean }> {
  await request('POST', '/evaluation/dimensions/reorder', { ids })
  return { success: true }
}

/** 规则试算（POST /evaluation/dimensions/{id}/calculate；门槛 evaluation:dim_manage） */
export async function calculateDimensionScore(
  dimension: Dimension,
  value: number
): Promise<{ score: number; matchedRule: { condition: string; value: number; score: number } | null }> {
  const dto = await request<ScoreDataDto>('POST', `/evaluation/dimensions/${dimension.id}/calculate`, {
    value,
  })
  const score = dto?.score ?? 0
  // 命中规则行本地推导（后端仅回 score；高亮展示用，规则按序匹配命中首条即停）
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
  const dto = await request<DimensionHealthCheckDataDto>(
    'GET',
    `/evaluation/dimensions/${dimension.id}/health`
  )
  return toDimensionHealthCheck(dto)
}

/** 复制维度（后端无独立 duplicate 端点：以「{原名}（副本）」为名 POST 创建，配置深拷贝） */
export async function duplicateDimension(
  dimension: Dimension
): Promise<{ success: boolean }> {
  const body = toDimensionInputDto({
    ...dimension,
    name: `${dimension.name}（副本）`,
  })
  await request('POST', '/evaluation/dimensions', body)
  return { success: true }
}

/** 保存分类（新增/编辑；有 id 走 PUT /categories/{id}，无 id 走 POST；门槛 category_manage） */
export async function saveEvaluationCategory(
  input: Partial<EvaluationCategory>
): Promise<{ success: boolean }> {
  const body = toCategoryInputDto(input)
  if (input.id != null) {
    await request('PUT', `/evaluation/categories/${input.id}`, body)
  } else {
    await request('POST', '/evaluation/categories', body)
  }
  return { success: true }
}

/** 删除分类（DELETE /evaluation/categories/{id}；门槛 category_manage） */
export async function deleteEvaluationCategory(
  id: number
): Promise<{ success: boolean }> {
  await request('DELETE', `/evaluation/categories/${id}`)
  return { success: true }
}

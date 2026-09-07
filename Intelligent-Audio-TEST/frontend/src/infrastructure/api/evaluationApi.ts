/**
 * Evaluation API module
 * HTTP 通道层：所有方法经 evaluationAdapter 做 snake_case ⇄ camelCase 转换
 * 对外只暴露 camelCase Domain 类型（domain/model/dimension）
 */
import type {
  Dimension,
  EvaluationCategory,
  EvaluationCategoryList,
  DimensionOptionsResult,
} from '../../domain/model/dimension'
import type { DimensionHealthCheckResult } from '../../domain/model/evaluationTypes'
import type { Paginated } from '../../domain/model/common'
import type { RequestOptions } from '../http/client'
import { request } from '../http/client'
import {
  toDimension,
  toDimensionPage,
  toDimensionOptions,
  toDimensionHealthCheck,
  toScore,
  toDimensionImportResult,
  toEvaluationCategory,
  toEvaluationCategoryList,
  toDimensionDto,
  toCategoryDto,
} from '../adapters/evaluationAdapter'

/** 通用查询参数（camelCase → snake_case 由本方法完成） */
interface DimensionQueryParams {
  page?: number
  perPage?: number
  search?: string
  status?: boolean | string
  categoryId?: number | string
  algorithmType?: string
}

/** 将 camelCase 查询参数转为 snake_case（仅供 evaluationApi 内部使用） */
function toDimensionQueryParams(params: DimensionQueryParams): Record<string, any> {
  const snakeParams: Record<string, any> = {}
  if (params.page !== undefined) snakeParams.page = params.page
  if (params.perPage !== undefined) snakeParams.per_page = params.perPage
  if (params.search !== undefined) snakeParams.search = params.search
  if (params.status !== undefined) snakeParams.status = params.status
  if (params.categoryId !== undefined) snakeParams.category_id = params.categoryId
  if (params.algorithmType !== undefined) snakeParams.algorithm_type = params.algorithmType
  return snakeParams
}

export const evaluationApi = {
  /** 获取维度分页列表 */
  async getAll(params: DimensionQueryParams = {}, options: RequestOptions = {}): Promise<Paginated<Dimension>> {
    const snakeParams = toDimensionQueryParams(params)
    const raw = await request<any>('GET', '/evaluation/dimensions', null, { ...options, params: snakeParams })
    return toDimensionPage(raw)
  },

  /** 获取维度选项（下拉框用） */
  async getOptions(params: { algorithmType?: string } = {}): Promise<DimensionOptionsResult> {
    const snakeParams: Record<string, any> = {}
    if (params.algorithmType) snakeParams.algorithm_type = params.algorithmType
    const raw = await request<any>('GET', '/evaluation/dimensions/options', null, { params: snakeParams })
    return toDimensionOptions(raw)
  },

  /** 获取单个维度 */
  async getOne(id: string | number): Promise<Dimension> {
    const raw = await request<any>('GET', `/evaluation/dimensions/${id}`)
    return toDimension(raw)
  },

  /** 创建维度 */
  async create(dimData: Partial<Dimension>): Promise<Dimension> {
    const raw = await request<any>('POST', '/evaluation/dimensions', toDimensionDto(dimData))
    return toDimension(raw)
  },

  /** 更新维度 */
  async update(id: string | number, dimData: Partial<Dimension>): Promise<void> {
    await request<void>('PUT', `/evaluation/dimensions/${id}`, toDimensionDto(dimData))
  },

  /** 删除维度 */
  async delete(id: string | number): Promise<void> {
    await request<void>('DELETE', `/evaluation/dimensions/${id}`)
  },

  /** API 健康检查 */
  async healthCheck(id: string | number): Promise<DimensionHealthCheckResult> {
    const raw = await request<any>('GET', `/evaluation/dimensions/${id}/health`)
    return toDimensionHealthCheck(raw)
  },

  /** 批量操作 */
  async batchAction(action: string, ids: (string | number)[]): Promise<any> {
    return request<any>('POST', '/evaluation/dimensions/batch', { action, item_ids: ids })
  },

  /** 计算评分 */
  async calculateScore(id: string | number, value: any): Promise<number> {
    const raw = await request<any>('POST', `/evaluation/dimensions/${id}/calculate`, { value })
    return toScore(raw)
  },

  /** 导入维度 */
  async import(formData: FormData, updateExisting: boolean = false): Promise<{ imported: number; updated: number }> {
    formData.append('update_existing', updateExisting.toString())
    const raw = await request<any>('POST', '/evaluation/dimensions/import', formData, { isMultipart: true })
    return toDimensionImportResult(raw)
  },

  /** 导出维度 */
  async export(format: 'json' | 'excel' = 'json', ids?: (string | number)[], options: RequestOptions = {}): Promise<any> {
    const params: any = { format }
    if (ids && ids.length > 0) {
      params.ids = ids.join(',')
    }
    return request<any>('GET', '/evaluation/dimensions/export', null, { ...options, params, responseType: 'blob' })
  },

  /** 获取分类列表 */
  async getCategories(): Promise<EvaluationCategoryList> {
    const raw = await request<any>('GET', '/evaluation/categories')
    return toEvaluationCategoryList(raw)
  },

  /** 创建分类 */
  async createCategory(catData: Partial<EvaluationCategory>): Promise<EvaluationCategory> {
    const raw = await request<any>('POST', '/evaluation/categories', toCategoryDto(catData))
    return toEvaluationCategory(raw)
  },

  /** 更新分类 */
  async updateCategory(id: string | number, catData: Partial<EvaluationCategory>): Promise<void> {
    await request<void>('PUT', `/evaluation/categories/${id}`, toCategoryDto(catData))
  },

  /** 删除分类 */
  async deleteCategory(id: string | number): Promise<void> {
    await request<void>('DELETE', `/evaluation/categories/${id}`)
  }
}

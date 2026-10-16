/**
 * 评估维度领域模型（domain 层；11_用例域.md §3.4 评估维度 facet）。
 * 形态对照 api_gateway/schemas/evaluation.py DimensionItem 实测子集：
 * id/name/dimension_type/parent_dimension_id/category_id/weight/status。
 * 本卡消费「评估维度」facet 选项（主维度，type≠sub 过滤，照现 loadDimensionOptions 口径）；
 * 完整维度管理模型归评估维度页卡（features/evaluation）。
 */

export interface EvaluationDimensionItem {
  id: number
  name: string
  description: string | null
  /** main 主维度 / sub 子维度 */
  dimensionType: 'main' | 'sub' | null
  parentDimensionId: number | null
  categoryId: number | null
  weight: number | null
  status: boolean | null
  createdAt: string | null
  updatedAt: string | null
}

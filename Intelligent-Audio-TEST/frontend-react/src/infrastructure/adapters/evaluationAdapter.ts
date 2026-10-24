/**
 * 评估维度 DTO→Domain 适配器（infrastructure/adapters 层；11_用例域.md §10 契约）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；Presentation 层不感知 snake_case。
 * INT-714 接线 read 路径（音频导入上传选项/用例 facet 消费真实维度与算法选项）。
 */
import type {
  EvaluationCategory,
  EvaluationDimensionItem,
} from '@/domain/models/evaluationDimension'
import type {
  CategoryItemDto,
  DimensionItemDto,
} from '@/infrastructure/dto/evaluation.dto'

const MAIN_TYPE = new Set(['main'])

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

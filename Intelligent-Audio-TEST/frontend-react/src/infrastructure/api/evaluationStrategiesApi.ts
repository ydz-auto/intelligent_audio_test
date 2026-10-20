/**
 * 评估策略 API（infrastructure 层；11_用例域.md §5.1.3 评估策略节）。
 * 后端实体 INT-590 已 done（evaluation_strategy_bp.py 前缀 /evaluation-strategies）：
 *   GET  /api/v1/evaluation-strategies    策略列表（EvaluationStrategyListData 信封）
 *   POST /api/v1/evaluation-strategies    新建策略（StringIdData 返回 id）
 * snake_case↔camelCase 转换收敛在 adapters/evaluationStrategyAdapter。
 */
import { apiClient } from './client'
import type { EvaluationStrategy } from '@/domain/models/evaluationStrategy'
import {
  evaluationStrategyFromDto,
  evaluationStrategyToDto,
  type EvaluationStrategyListItemDto,
} from '@/infrastructure/adapters/evaluationStrategyAdapter'

/** GET /evaluation-strategies 分页信封（EvaluationStrategyListData） */
interface EvaluationStrategyListDto {
  items?: EvaluationStrategyListItemDto[]
  total?: number
  page?: number
  per_page?: number
  pages?: number
}

/** 策略列表（选项带摘要「{名} · 整体维度 {n} 项 · 噪声 {已配置|未配置}」） */
export async function fetchEvaluationStrategies(): Promise<EvaluationStrategy[]> {
  const dto = await apiClient.get<EvaluationStrategyListDto>('/evaluation-strategies', {
    params: { per_page: 200 },
  })
  return (dto?.items ?? []).map(evaluationStrategyFromDto)
}

/** 新建策略（POST /evaluation-strategies；入库后进入 Select 列表全局可复用） */
export async function createEvaluationStrategy(
  input: Pick<EvaluationStrategy, 'name' | 'description'> &
    Partial<Pick<EvaluationStrategy, 'dimensions' | 'backgroundNoise'>>
): Promise<EvaluationStrategy> {
  const dto = await apiClient.post<{ id?: string | number }>(
    '/evaluation-strategies',
    evaluationStrategyToDto(input)
  )
  return {
    id: dto?.id ?? '',
    name: input.name,
    description: input.description ?? null,
    dimensions: input.dimensions ?? [],
    backgroundNoise: input.backgroundNoise ?? null,
  }
}

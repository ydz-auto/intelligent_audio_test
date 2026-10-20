/**
 * 评估策略序列化适配器（infrastructure/adapters 层；snake_case 只在此层出现）。
 * 后端策略实体 INT-590 已 done（evaluation_strategy_bp.py：GET/POST /evaluation-strategies，
 * schemas/evaluation_strategy.py EvaluationStrategyListItem）。
 * 列表项 config 包裹 { dimensions, background_noise }；维度条目字段照
 * EvaluationStrategyDimensionItem（llmJudgeConfig 为 camelCase 字段名；round_scope
 * 别名 roundScope——前端只消费 id/name/weight/threshold/llmJudgeConfig）。
 */
import type { EvaluationStrategy } from '@/domain/models/evaluationStrategy'

/** 策略列表项 DTO（EvaluationStrategyListItem + config 包裹） */
export interface EvaluationStrategyListItemDto {
  id: number | string
  name: string
  description?: string | null
  algorithm_type?: string | null
  enabled?: boolean
  config?: {
    dimensions?: Array<{
      id?: number | string | null
      name?: string | null
      display_name?: string | null
      weight?: number | null
      threshold?: number | null
      llmJudgeConfig?: Record<string, unknown> | null
    }>
    background_noise?: Record<string, unknown> | null
  }
  referenced_case_count?: number
  created_at?: string | null
  updated_at?: string | null
}

/** DTO → Domain（config 包裹解出 dimensions/background_noise；LLM 配置子字段一并转） */
export function evaluationStrategyFromDto(
  dto: EvaluationStrategyListItemDto
): EvaluationStrategy {
  const config = dto.config ?? {}
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? null,
    dimensions: (config.dimensions ?? []).map((d) => ({
      id: d.id ?? d.name ?? '',
      name: d.name ?? d.display_name ?? '',
      weight: d.weight ?? 50,
      threshold: d.threshold ?? 80,
      ...(d.llmJudgeConfig
        ? {
            llmJudgeConfig: {
              model: String(d.llmJudgeConfig.model ?? ''),
              promptTemplate: String(
                d.llmJudgeConfig.prompt_template ?? d.llmJudgeConfig.promptTemplate ?? ''
              ),
            },
          }
        : {}),
    })),
    backgroundNoise: config.background_noise
      ? (() => {
          const bn = config.background_noise
          return {
            audioId: (bn.audio_id ?? null) as number | string | null,
            audioName: (bn.audio_name ?? null) as string | null,
            spl: bn.spl != null ? Number(bn.spl) : null,
            deviceIds: Array.isArray(bn.device_ids) ? bn.device_ids : [],
            deviceNames: Array.isArray(bn.device_names) ? bn.device_names : [],
            loop: bn.loop == null ? true : Boolean(bn.loop),
          }
        })()
      : null,
  }
}

/** Domain → POST 载荷（EvaluationStrategyCreateSchema：name/description/config 包裹） */
export function evaluationStrategyToDto(
  strategy: Pick<EvaluationStrategy, 'name' | 'description'> &
    Partial<Pick<EvaluationStrategy, 'dimensions' | 'backgroundNoise'>>
): Record<string, unknown> {
  return {
    name: strategy.name,
    description: strategy.description ?? '',
    algorithm_type: null,
    enabled: true,
    config: {
      dimensions: (strategy.dimensions ?? []).map((d) => ({
        id: d.id,
        name: d.name,
        weight: d.weight,
        threshold: d.threshold,
        ...(d.llmJudgeConfig
          ? {
              llmJudgeConfig: {
                model: d.llmJudgeConfig.model,
                prompt_template: d.llmJudgeConfig.promptTemplate,
              },
            }
          : {}),
      })),
      background_noise: strategy.backgroundNoise
        ? {
            audio_id: strategy.backgroundNoise.audioId ?? null,
            audio_name: strategy.backgroundNoise.audioName ?? null,
            spl: strategy.backgroundNoise.spl ?? null,
            device_ids: strategy.backgroundNoise.deviceIds ?? [],
            device_names: strategy.backgroundNoise.deviceNames ?? [],
            loop: strategy.backgroundNoise.loop ?? true,
          }
        : null,
    },
  }
}

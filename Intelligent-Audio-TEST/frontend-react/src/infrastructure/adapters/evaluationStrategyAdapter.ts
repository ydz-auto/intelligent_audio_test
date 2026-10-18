/**
 * 评估策略序列化适配器（infrastructure/adapters 层；snake_case 只在此层出现）。
 * 后端策略实体由 INT-590 落定（GET/POST /evaluation/strategies）——当前 mock 阶段
 * Domain 即最终形态；本适配器按契约先立（DTO snake_case ↔ Domain camelCase），
 * 后端策略卡 done 后直接启用，interfaces 层无感。
 */
import type { EvaluationStrategy } from '@/domain/models/evaluationStrategy'

/** 策略列表项 DTO（snake_case 契约草案：id/name/description/dimensions[]/background_noise） */
export interface EvaluationStrategyDto {
  id: number | string
  name: string
  description?: string | null
  dimensions?: Array<{
    id: number | string
    name: string
    weight: number
    threshold: number
    llm_judge_config?: { model: string; prompt_template: string } | null
  }>
  background_noise?: {
    audio_id?: number | string | null
    audio_name?: string | null
    spl?: number | null
    device_ids?: Array<number | string>
    device_names?: string[]
    loop?: boolean
  } | null
}

/** DTO → Domain（snake_case 转 camelCase；LLM 配置子字段一并转） */
export function evaluationStrategyFromDto(dto: EvaluationStrategyDto): EvaluationStrategy {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? null,
    dimensions: (dto.dimensions ?? []).map((d) => ({
      id: d.id,
      name: d.name,
      weight: d.weight,
      threshold: d.threshold,
      ...(d.llm_judge_config
        ? {
            llmJudgeConfig: {
              model: d.llm_judge_config.model,
              promptTemplate: d.llm_judge_config.prompt_template,
            },
          }
        : {}),
    })),
    backgroundNoise: dto.background_noise
      ? {
          audioId: dto.background_noise.audio_id ?? null,
          audioName: dto.background_noise.audio_name ?? null,
          spl: dto.background_noise.spl ?? null,
          deviceIds: dto.background_noise.device_ids ?? [],
          deviceNames: dto.background_noise.device_names ?? [],
          loop: dto.background_noise.loop ?? true,
        }
      : null,
  }
}

/** Domain → DTO（POST 载荷；新建策略提交用） */
export function evaluationStrategyToDto(
  strategy: Pick<EvaluationStrategy, 'name' | 'description'> &
    Partial<Pick<EvaluationStrategy, 'dimensions' | 'backgroundNoise'>>
): Record<string, unknown> {
  return {
    name: strategy.name,
    description: strategy.description ?? '',
    dimensions: (strategy.dimensions ?? []).map((d) => ({
      id: d.id,
      name: d.name,
      weight: d.weight,
      threshold: d.threshold,
      ...(d.llmJudgeConfig
        ? {
            llm_judge_config: {
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
  }
}

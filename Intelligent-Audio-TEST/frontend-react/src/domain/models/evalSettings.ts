/**
 * 评估服务设置领域模型（domain 层，camelCase、零依赖）。
 *
 * 对应后端 shared/config/eval_settings.py：键 = `eval.<分区>.<字段>`；
 * 密钥类字段不在 KV 里（只经密钥接口写入、掩码回显），因此不出现在本模型。
 */
import {
  parseBoolean,
  parseNumber,
  parseString,
  type SystemOptions,
} from './option'

/** 分维度模型支持的维度标识（与 eval_server config.LLM_JUDGE 对齐） */
export const EVAL_LLM_DIMENSIONS = [
  { id: 'turn_eval', label: '话轮评估' },
  { id: 'high_freq_llm_judge', label: '高频裁判' },
  { id: 'false_takeover', label: '误接管' },
  { id: 'reply_quality', label: '回复质量' },
  { id: 'interruption_judge', label: '打断裁判' },
  { id: 'reject_judge', label: '拒识裁判' },
  { id: 'env_judge', label: '环境理解' },
] as const

/** 维度专用模型的选项键（一维一键） */
export function evalDimensionModelKey(dimension: string): string {
  return `eval.llm.model.${dimension}`
}

export type EvalLlmSettings = {
  apiBase: string
  defaultModel: string
  maxTokens: number
  temperature: number
  timeout: number
  audioCompress: string
  dimensionModels: Record<string, string>
}

export type EvalAsrSettings = {
  url: string
  timeout: number
}

export type EvalRelaySettings = {
  selfZone: string
  hubZone: string
  syncBackZone: string
  triggerEnabled: boolean
  cApiBaseUrl: string
  fallbackUrls: string
}

export const EVAL_LLM_OPTION_KEYS: Record<keyof EvalLlmSettings, string> = {
  apiBase: 'eval.llm.api_base',
  defaultModel: 'eval.llm.default_model',
  maxTokens: 'eval.llm.max_tokens',
  temperature: 'eval.llm.temperature',
  timeout: 'eval.llm.timeout',
  audioCompress: 'eval.llm.audio_compress',
  dimensionModels: 'eval.llm.dimension_models',
}

export const EVAL_ASR_OPTION_KEYS: Record<keyof EvalAsrSettings, string> = {
  url: 'eval.asr.url',
  timeout: 'eval.asr.timeout',
}

export const EVAL_RELAY_OPTION_KEYS: Record<keyof EvalRelaySettings, string> = {
  selfZone: 'eval.relay.self_zone',
  hubZone: 'eval.relay.hub_zone',
  syncBackZone: 'eval.relay.sync_back_zone',
  triggerEnabled: 'eval.relay.trigger_enabled',
  cApiBaseUrl: 'eval.relay.c_api_base_url',
  fallbackUrls: 'eval.relay.fallback_urls',
}

/** 密钥键（只经 /api/option/secrets 读写） */
export const EVAL_SECRET_KEYS = {
  llmApiKey: 'eval.llm.api_key',
  relayTokenAB: 'eval.relay.token_a_b',
  relayTokenBC: 'eval.relay.token_b_c',
} as const

export function resolveEvalLlmSettings(options: SystemOptions): EvalLlmSettings {
  const dimensionModels: Record<string, string> = {}
  for (const dimension of EVAL_LLM_DIMENSIONS) {
    const value = parseString(
      options[evalDimensionModelKey(dimension.id)],
      ''
    )
    if (value) dimensionModels[dimension.id] = value
  }
  return {
    apiBase: parseString(options[EVAL_LLM_OPTION_KEYS.apiBase], ''),
    defaultModel: parseString(options[EVAL_LLM_OPTION_KEYS.defaultModel], ''),
    maxTokens: parseNumber(options[EVAL_LLM_OPTION_KEYS.maxTokens], 0),
    temperature: parseNumber(options[EVAL_LLM_OPTION_KEYS.temperature], -1),
    timeout: parseNumber(options[EVAL_LLM_OPTION_KEYS.timeout], 0),
    audioCompress: parseString(options[EVAL_LLM_OPTION_KEYS.audioCompress], ''),
    dimensionModels,
  }
}

export function resolveEvalAsrSettings(options: SystemOptions): EvalAsrSettings {
  return {
    url: parseString(options[EVAL_ASR_OPTION_KEYS.url], ''),
    timeout: parseNumber(options[EVAL_ASR_OPTION_KEYS.timeout], 0),
  }
}

export function resolveEvalRelaySettings(
  options: SystemOptions
): EvalRelaySettings {
  return {
    selfZone: parseString(options[EVAL_RELAY_OPTION_KEYS.selfZone], ''),
    hubZone: parseString(options[EVAL_RELAY_OPTION_KEYS.hubZone], ''),
    syncBackZone: parseString(options[EVAL_RELAY_OPTION_KEYS.syncBackZone], ''),
    triggerEnabled: parseBoolean(
      options[EVAL_RELAY_OPTION_KEYS.triggerEnabled],
      false
    ),
    cApiBaseUrl: parseString(options[EVAL_RELAY_OPTION_KEYS.cApiBaseUrl], ''),
    fallbackUrls: parseString(options[EVAL_RELAY_OPTION_KEYS.fallbackUrls], ''),
  }
}

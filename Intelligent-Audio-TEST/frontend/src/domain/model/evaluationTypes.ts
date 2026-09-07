/**
 * LLM 评审配置（评估维度附属） —— camelCase
 */

/** 评估维度 LLM 评审配置 */
export interface LlmJudgeConfig {
  model?: string
  promptTemplate?: string
  maxTokens?: number
  temperature?: number
}

/** 维度 API 健康探测单项结果（对应 HealthCheckResultItem） */
export interface DimensionHealthCheckItem {
  url: string
  status: string
  statusCode?: number
  responseTime?: string
  message?: string
  error?: string
}

/** 维度 API 健康探测结果（对应 DimensionHealthCheckData） */
export interface DimensionHealthCheckResult {
  results: DimensionHealthCheckItem[]
  overallStatus: string
}

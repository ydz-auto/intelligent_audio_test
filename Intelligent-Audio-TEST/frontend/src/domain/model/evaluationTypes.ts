/**
 * LLM 评审配置 —— 历史字段，只读兼容（INT-1868 裁定 A 后后端无此能力：
 * 模型 / Prompt / Token / Temperature 均撤除，前端不再提供编辑入口、不再写入）
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

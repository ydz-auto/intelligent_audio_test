/**
 * Evaluation（评估维度）领域模型 —— camelCase
 * 对应后端 api_gateway/schemas/evaluation.py::DimensionItem / CategoryItem
 *
 * 枚举值保持后端原值（如 'main' / 'sub' / 'auto' / 'average'），只转字段名。
 */
import type { LlmJudgeConfig } from './evaluationTypes'

/** 维度关联的算法（对应后端 associated_algorithms 列表项） */
export interface AlgorithmAssociation {
  algorithmType: string
  isDefault: boolean
  weight: number
}

/** 维度 API 端点配置（apiEndpoints 列表项） */
export interface DimensionApiEndpoint {
  url: string
  name: string
  priority: number
  maxProcess: number
  maxTimeout: number
  maxAudioDuration: number
}

/** 维度 API 设置（api_settings JSON 对象） */
export interface DimensionApiSettings {
  [key: string]: unknown
}

/** 评分规则（rule 字段：对象或 JSON 字符串，结构保持宽松但不开放索引签名） */
export interface DimensionRule {
  [key: string]: unknown
}

/** 评估维度完整模型（对应 DimensionItem） */
export interface Dimension {
  id: number | string
  name: string
  /** 维度编码（前端本地字段，历史消费方使用；后端无直接对应） */
  code?: string
  description?: string
  keywords?: string
  /** 维度类型（后端 dimension_type 原值） */
  dimensionType?: 'main' | 'sub' | (string & {})
  parentDimensionId?: number | null
  taskTypeCode?: string
  categoryId?: number
  apiUrl?: string
  apiEndpoints?: DimensionApiEndpoint[]
  apiSettings?: DimensionApiSettings | string
  apiStatus?: string
  /** 评分类型（后端 type 原值） */
  type?: string
  /** 结果类型（后端原值为 int） */
  resultType?: number
  resultMin?: number
  resultMax?: number
  decimalPlaces?: number
  weight?: number
  /** 预计执行时间（秒） */
  estimatedExecTime?: number
  /** 评分规则（对象或 JSON 字符串） */
  rule?: DimensionRule | string
  requiredInputs?: string
  outputFields?: unknown[]
  /** 统计方式（后端 statistic_method 原值） */
  statisticMethod?: string
  associatedAlgorithms?: AlgorithmAssociation[]
  /** 启用状态（后端原值为 bool） */
  status?: boolean
  createdAt?: string
  updatedAt?: string
  /** 评分单位 */
  scoreUnit?: string
  /** LLM 评审配置（维度附属） */
  llmJudgeConfig?: LlmJudgeConfig
  /** 前端本地字段：是否需要音频输入（历史消费方使用） */
  requiresAudio?: boolean
}

export type EvaluationDimension = Dimension

/** 评估分类（对应 CategoryItem） */
export interface EvaluationCategory {
  id: number
  name: string
  description?: string
  icon?: string
  createdAt?: string
  updatedAt?: string
}

/** 分类列表（对应 CategoryListData：items + total 包装） */
export interface EvaluationCategoryList {
  items: EvaluationCategory[]
  total: number
}

/** 维度选项（下拉框用，对应 get_dimension_options 返回项） */
export interface DimensionOption {
  id: number | string
  name: string
  /** 关联算法类型 */
  algorithmType?: string
  /** 是否默认维度 */
  isDefault?: boolean
  weight?: number
  /** 维度描述 */
  description?: string
  /** 维度类型（后端原值） */
  type?: string
}

/** 维度选项响应（对应 options 接口 { dimensions: [...] } 包装） */
export interface DimensionOptionsResult {
  dimensions: DimensionOption[]
}

/** 重评任务结果（对应 TaskReevaluateResult） */
export interface TaskReevaluateResult {
  totalCases: number
  queuedCases: number
  reextractedCases: number
  message: string
}

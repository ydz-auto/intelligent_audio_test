/**
 * 评估维度领域模型（domain 层；11_用例域.md §3.4 评估维度 facet + §4.1 评估维度页）。
 * 形态对照 api_gateway/schemas/evaluation.py DimensionItem / CategoryItem 实测，
 * snake_case 仅存在于 infrastructure 层，前端 Domain 一律 camelCase（基座规范 §10.1）。
 * EvaluationDimensionItem 为 facet 消费子集（主维度，type≠sub 过滤，照 loadDimensionOptions 口径）；
 * 完整维度管理模型（Dimension + EvaluationCategory）归本页卡（features/evaluation）。
 */

/** LLM Judge 配置（dimension.llmJudgeConfig，§5.5 结果配置节） */
export interface LlmJudgeConfig {
  model: string
  promptTemplate: string
  maxTokens: number
  temperature: number
}

/** 维度关联的算法（associated_algorithms 列表项） */
export interface AlgorithmAssociation {
  algorithmType: string
  isDefault: boolean
  weight: number
}

/** 维度 API 端点配置（api_endpoints 列表项） */
export interface DimensionApiEndpoint {
  url: string
  name: string
  priority: number
  maxProcess: number
  maxTimeout: number
  maxAudioDuration: number
}

/** 维度 API 设置（api_settings JSON 对象；结构宽松不开放索引签名） */
export interface DimensionApiSettings {
  method?: string
  headers?: Record<string, string>
  bodyTemplate?: unknown
  timeout?: number
  [key: string]: unknown
}

/** 评分规则（rule 字段；规则行 condition 为比较符原始值） */
export interface DimensionRule {
  rules?: Array<{
    condition: string
    value: number
    score: number
  }>
  [key: string]: unknown
}

/** 所需输入配置（required_inputs 列表项） */
export interface DimensionRequiredInput {
  key: string
  label: string
  fieldType: string
  required: boolean
  defaultValue?: unknown
  description?: string
}

/** 输出字段配置（output_fields 列表项） */
export interface DimensionOutputField {
  name: string
  label: string
  outputRole: string
  aggRole: string
  defaultValue?: unknown
}

/** 评估维度完整模型（DimensionItem） */
export interface Dimension {
  id: number | string
  name: string
  description?: string | null
  /** 搜索关键词（keywords，主维度；占位「如：准确,精度」） */
  keywords?: string | null
  /** main 主维度 / sub 子维度 */
  dimensionType?: 'main' | 'sub' | null
  parentDimensionId?: number | null
  categoryId?: number | null
  apiUrl?: string | null
  apiEndpoints?: DimensionApiEndpoint[]
  apiSettings?: DimensionApiSettings | string
  /** online / offline / llm_judge */
  apiStatus?: string | null
  scoreUnit?: string | null
  /** 评估类型（type 原值：auto/manual） */
  type?: string | null
  /** 结果类型（后端原值 int；llm_judge 字符串兼容判「LLM Judge」徽章） */
  resultType?: number | 'llm_judge' | null
  resultMin?: number | null
  resultMax?: number | null
  decimalPlaces?: number | null
  /** 权重（1-10 整数滑杆） */
  weight?: number | null
  sortOrder?: number | null
  estimatedExecTime?: number | null
  rule?: DimensionRule | string | null
  requiredInputs?: DimensionRequiredInput[] | null
  outputFields?: DimensionOutputField[] | null
  statisticMethod?: string | null
  aggDenominator?: string | null
  excludeRounds?: number[] | null
  associatedAlgorithms?: AlgorithmAssociation[] | null
  /** 启用状态（后端原值 bool） */
  status?: boolean | null
  createdAt?: string | null
  updatedAt?: string | null
  llmJudgeConfig?: LlmJudgeConfig | null
}

/** 评估分类（CategoryItem；无 status 字段） */
export interface EvaluationCategory {
  id: number
  name: string
  description?: string | null
  icon?: string | null
  createdAt?: string | null
  updatedAt?: string | null
}

/** API 健康测试结果项（HealthCheckResultItem） */
export interface HealthCheckResultItem {
  url: string
  status: string
  statusCode?: number | null
  responseTime?: string | null
  message?: string | null
  error?: string | null
}

/** API 健康测试结果（DimensionHealthCheckData） */
export interface DimensionHealthCheckData {
  results: HealthCheckResultItem[]
  overallStatus: string
}

/** 试算结果（ScoreData） */
export interface ScoreData {
  score: number
}

/**
 * 评估维度 facet 选项子集（EvaluationDimensionItem；facet singleSelect 消费）。
 * 完整字段见 Dimension。
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
  /** 是否默认评估维度（后端 is_default 语义；INT-646 代码审计 P3-3 与 status 解耦） */
  isDefault?: boolean | null
  /** 启用状态（Dimension 全字段子集；options 端点不下发，恒 null） */
  status: boolean | null
  createdAt: string | null
  updatedAt: string | null
}

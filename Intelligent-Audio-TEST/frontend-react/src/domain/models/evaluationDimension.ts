/**
 * 评估维度领域模型（domain 层；11_用例域.md §3.4 评估维度 facet + §4.1 评估维度页）。
 * 形态对照 api_gateway/schemas/evaluation.py DimensionItem / CategoryItem 实测，
 * snake_case 仅存在于 infrastructure 层，前端 Domain 一律 camelCase（基座规范 §10.1）。
 * EvaluationDimensionItem 为 facet 消费子集（主维度，type≠sub 过滤，照 loadDimensionOptions 口径）；
 * 完整维度管理模型（Dimension + EvaluationCategory）归本页卡（features/evaluation）。
 */

/**
 * LLM Judge 配置（dimension.llmJudgeConfig）。
 * INT-1671 裁定 A：平台没有模型 / Prompt 枚举能力，维度表单不再编辑、保存侧不再写入；
 * 仅作历史数据只读原样透传，不删不清、不补默认值。
 */
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

/**
 * 所需输入配置（required_inputs 列表项）。
 * 字段对照 evaluation_service 序列化（_serialize_dimension_param）：
 * param_code / param_name / label / field_type / required / default_value / help_text / ui_order。
 * 兼容旧数据 key/description 键（adapter 归一为 paramCode/helpText）。
 */
export interface DimensionRequiredInput {
  id?: number | null
  dimensionId?: number | null
  /** 参数键名（param_code，如 asr_result） */
  paramCode: string
  /** 参数名称（param_name，如 ASR识别结果） */
  paramName: string
  /** 显示标签（label，缺省回退 paramName） */
  label: string
  /** 字段类型（field_type 原值：text/number/audio/boolean/json/timestamp） */
  fieldType: string
  required: boolean
  defaultValue?: unknown
  /** 帮助文本（help_text；兼容旧数据 description） */
  helpText?: string
  /** 展示顺序（ui_order） */
  uiOrder?: number | null
}

/**
 * 输出字段配置（output_fields 列表项）。
 * 字段对照 evaluation_service 序列化：param_code / param_name / label / field_path /
 * field_type / output_role / agg_role / default_value / visible_in_report / help_text / ui_order。
 * 兼容旧数据 name 键（adapter 归一为 paramCode）。
 */
export interface DimensionOutputField {
  id?: number | null
  dimensionId?: number | null
  /** 字段代码（param_code，如 wer） */
  paramCode: string
  /** 参数名称（param_name，如 WER值） */
  paramName: string
  /** 显示标签（label，缺省回退 paramName） */
  label: string
  /** 提取路径（field_path，如 wer 或 data.result.wer） */
  fieldPath: string
  /** 字段类型（field_type 原值：number/text/boolean/json/timestamp） */
  fieldType: string
  /** 字段角色（output_role：main 主结果 / aux 辅助字段） */
  outputRole: string
  /** 聚合角色（agg_role：'' 无 / value 直接值 / numerator 分子 / denominator 分母 / pass_* 达标线） */
  aggRole: string
  defaultValue?: unknown
  /** 是否在报告中可见（visible_in_report） */
  visibleInReport: boolean
  /** 帮助文本（help_text） */
  helpText?: string
  /** 展示顺序（ui_order） */
  uiOrder?: number | null
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
  /** 结果类型（后端原值 int：1 数值 / 2 布尔 / 3 文本；LLM Judge 不是结果类型） */
  resultType?: number | null
  /**
   * 是否 LLM Judge 维度（后端派生布尔 llm_judge：由维度自身 task_type_code / dimension_type 判定）。
   * 只读徽章标识，前端不据此提供模型 / Prompt 选择（INT-1671 裁定 A）。
   */
  llmJudge?: boolean
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
  /** 历史 LLM Judge 配置（只读透传；表单不再编辑、保存侧不再写入） */
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

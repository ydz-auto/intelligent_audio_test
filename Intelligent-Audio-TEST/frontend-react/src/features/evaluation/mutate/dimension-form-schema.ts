/**
 * 评估维度表单 schema + 转换器（features/evaluation/mutate；11_用例域.md §5.5）。
 * 六分组节（基本信息/层级配置/结果配置/API配置/关联算法）字段常量与 RHF+zod schema；
 * 表单值类型由 schema 推导（DimensionFormValues），编辑态由 Dimension 反填、保存态
 * 收敛为 Partial<Dimension>（mock 阶段不真正提交）。
 */
import { z } from 'zod'

import type { Dimension } from '@/domain/models/evaluationDimension'
import {
  DEFAULT_CATEGORY_ICON,
  WEIGHT_MAX,
  WEIGHT_MIN,
} from '@/features/evaluation/constants'

/** 规则行（结果配置节「评分规则」编辑器行） */
export interface RuleRow {
  condition: string
  value: number
  score: number
}

/**
 * 所需输入配置行（API配置节「所需输入配置」编辑器行；对齐 DimensionRequiredInput：
 * paramCode / paramName / label / fieldType / required / defaultValue / helpText / uiOrder）。
 */
export interface RequiredInputRow {
  paramCode: string
  paramName: string
  label: string
  /** 字段类型（后端契约原值：text/number/audio/boolean/json/timestamp） */
  fieldType: string
  required: boolean
  defaultValue: string
  /** 帮助文本（help_text；兼容旧数据 description） */
  helpText: string
  /** 展示顺序（ui_order；缺省按行序） */
  uiOrder: number
}

/**
 * 输出字段配置行（API配置节「输出字段配置」编辑器行；对齐 DimensionOutputField：
 * paramCode / paramName / label / fieldPath / fieldType / outputRole / aggRole /
 * defaultValue / passThreshold / visibleInReport / helpText / uiOrder）。
 */
export interface OutputFieldRow {
  paramCode: string
  paramName: string
  label: string
  /** 提取路径（field_path，如 wer 或 data.result.wer） */
  fieldPath: string
  fieldType: string
  /** 字段角色（output_role：main 主结果 / aux 辅助字段） */
  outputRole: string
  /** 聚合角色（agg_role：'' 无 / value 直接值 / numerator 分子 / denominator 分母 / pass_* 达标线） */
  aggRole: string
  defaultValue: string
  /** 达标阈值（pass_threshold；聚合角色为达标线时后端按此判达标，照 V9.7.10 OutputFieldsEditor） */
  passThreshold: string
  /** 是否在报告中可见（visible_in_report） */
  visibleInReport: boolean
  helpText: string
  uiOrder: number
}

/** API 端点配置行（API配置节「API 端点配置」编辑器行；对齐 DimensionApiEndpoint） */
export interface ApiEndpointRow {
  url: string
  name: string
  priority: number
  maxProcess: number
  maxTimeout: number
  maxAudioDuration: number
}

/** 规则行 zod 字段（与 RuleRow 同构） */
const ruleRowSchema = z.object({
  condition: z.string(),
  value: z.number(),
  score: z.number(),
})

/** 所需输入/输出字段/API 端点子编辑器行 zod（P3-2 收敛进表单载荷，编辑态可反填） */
const requiredInputRowSchema = z.object({
  paramCode: z.string(),
  paramName: z.string(),
  label: z.string(),
  fieldType: z.string(),
  required: z.boolean(),
  defaultValue: z.string(),
  helpText: z.string(),
  uiOrder: z.number(),
})
const outputFieldRowSchema = z.object({
  paramCode: z.string(),
  paramName: z.string(),
  label: z.string(),
  fieldPath: z.string(),
  fieldType: z.string(),
  outputRole: z.string(),
  aggRole: z.string(),
  defaultValue: z.string(),
  passThreshold: z.string(),
  visibleInReport: z.boolean(),
  helpText: z.string(),
  uiOrder: z.number(),
})
const apiEndpointRowSchema = z.object({
  url: z.string(),
  name: z.string(),
  priority: z.number(),
  maxProcess: z.number(),
  maxTimeout: z.number(),
  maxAudioDuration: z.number(),
})

export const dimensionFormSchema = z
  .object({
    name: z.string().min(1, '维度名称不能为空'),
    description: z.string(),
    evaluationType: z.enum(['auto', 'manual']),
    categoryId: z.string(),
    status: z.boolean(),
    dimensionType: z.enum(['main', 'sub']),
    parentDimensionId: z.string(),
    keywords: z.string(),
    scoreUnit: z.string(),
    resultType: z.enum(['0', '1', '2', '3', 'llm_judge']),
    // valueAsNumber 下清空输入得 NaN，默认文案是英文（Invalid input: expected number…）；
    // 给中文文案，行内错误/页脚摘要才可读（INT-1551）
    resultMin: z.number({ error: '结果最小值请输入数字' }),
    resultMax: z.number({ error: '结果最大值请输入数字' }),
    decimalPlaces: z.number().min(0).max(4, '小数位数 0-4'),
    weight: z.number().min(WEIGHT_MIN).max(WEIGHT_MAX, '权重 1-10'),
    estimatedExecTime: z.number().min(1, '预计执行时间 ≥1 秒'),
    rule: z.array(ruleRowSchema).min(1, '请至少配置一条评分规则'),
    llmModel: z.string(),
    llmPromptTemplate: z.string(),
    llmMaxTokens: z.number().min(1).max(8192),
    llmTemperature: z.number().min(0).max(2),
    apiUrl: z.string(),
    apiMethod: z.enum(['GET', 'POST', 'PUT', 'DELETE', 'PATCH']),
    apiTimeout: z.number().min(1),
    apiHeaders: z.string(),
    apiBodyTemplate: z.string(),
    statisticMethod: z.string(),
    aggDenominator: z.string(),
    excludeRounds: z.array(z.string()),
    associatedAlgorithms: z.array(z.string()),
    requiredInputs: z.array(requiredInputRowSchema),
    outputFields: z.array(outputFieldRowSchema),
    apiEndpoints: z.array(apiEndpointRowSchema),
  })
  .superRefine((values, ctx) => {
    if (values.resultMin >= values.resultMax) {
      ctx.addIssue({
        code: 'custom',
        path: ['resultMax'],
        message: '结果最大值必须大于最小值',
      })
    }
    if (values.dimensionType === 'sub' && !values.parentDimensionId) {
      ctx.addIssue({
        code: 'custom',
        path: ['parentDimensionId'],
        message: '子维度请选择所属主维度',
      })
    }
  })

/** 表单值类型（由 schema 推导，保证 RHF resolver 类型对齐） */
export type DimensionFormValues = z.infer<typeof dimensionFormSchema>

/** 空表单初值（新增/复制） */
export function emptyDimensionFormValues(): DimensionFormValues {
  return {
    name: '',
    description: '',
    evaluationType: 'auto',
    categoryId: '',
    status: true,
    dimensionType: 'main',
    parentDimensionId: '',
    keywords: '',
    scoreUnit: '',
    resultType: '1',
    resultMin: 0,
    resultMax: 100,
    decimalPlaces: 2,
    weight: 5,
    estimatedExecTime: 5,
    rule: [
      { condition: '>=', value: 95, score: 10 },
      { condition: '>=', value: 90, score: 9 },
      { condition: '>=', value: 80, score: 8 },
      { condition: '>=', value: 70, score: 7 },
      { condition: '<', value: 70, score: 0 },
    ],
    llmModel: '',
    llmPromptTemplate: '',
    llmMaxTokens: 1024,
    llmTemperature: 0.7,
    apiUrl: '',
    apiMethod: 'POST',
    apiTimeout: 30000,
    apiHeaders: '{\n  "content-type": "application/json"\n}',
    apiBodyTemplate: '{\n  "rounds": [\n    { "answer": "{{answer}}", "correctAnswer": "{{correct_answer}}" }\n  ]\n}',
    statisticMethod: 'average',
    aggDenominator: 'case',
    excludeRounds: [],
    associatedAlgorithms: [],
    requiredInputs: [
      {
        paramCode: 'asr_result',
        paramName: 'ASR识别结果',
        label: 'ASR识别结果',
        fieldType: 'text',
        required: true,
        defaultValue: '',
        helpText: 'ASR算法识别出的文本',
        uiOrder: 1,
      },
      {
        paramCode: 'asr_ref',
        paramName: '参考文本',
        label: '参考文本',
        fieldType: 'text',
        required: true,
        defaultValue: '',
        helpText: '标准参考文本',
        uiOrder: 2,
      },
    ],
    outputFields: [
      {
        paramCode: 'score',
        paramName: '评分结果',
        label: '评分结果',
        fieldPath: 'score',
        fieldType: 'number',
        outputRole: 'main',
        aggRole: 'value',
        defaultValue: '',
        passThreshold: '',
        visibleInReport: true,
        helpText: '',
        uiOrder: 1,
      },
    ],
    apiEndpoints: [
      {
        url: 'https://api.example.com/evaluation/accuracy',
        name: '主评估端点',
        priority: 1,
        maxProcess: 5,
        maxTimeout: 30,
        maxAudioDuration: 60,
      },
    ],
  }
}

/** 编辑态 Dimension → 表单值（反填） */
export function toDimensionFormValues(dimension: Dimension): DimensionFormValues {
  const rules = Array.isArray(dimension.rule)
    ? dimension.rule
    : typeof dimension.rule === 'object' && dimension.rule?.rules
      ? dimension.rule.rules
      : []
  const ruleRows: RuleRow[] = rules.map((r) => ({
    condition: String(r.condition),
    value: Number(r.value),
    score: Number(r.score),
  }))
  // 子编辑器反填（P3-2）：缺省（null/空）时回退默认行，保证编辑态可继续编辑
  const requiredInputs = (dimension.requiredInputs ?? []).map((ri) => ({
    paramCode: ri.paramCode ?? '',
    paramName: ri.paramName ?? ri.label ?? '',
    label: ri.label ?? ri.paramName ?? '',
    fieldType: ri.fieldType ?? 'text',
    required: ri.required === undefined ? true : !!ri.required,
    defaultValue: formDefaultValue(ri.defaultValue),
    helpText: ri.helpText ?? '',
    uiOrder: ri.uiOrder ?? 0,
  }))
  const outputFields = (dimension.outputFields ?? []).map((of) => ({
    paramCode: of.paramCode ?? '',
    paramName: of.paramName ?? of.label ?? '',
    label: of.label ?? of.paramName ?? '',
    fieldPath: of.fieldPath ?? of.paramCode ?? '',
    fieldType: of.fieldType ?? 'number',
    outputRole: of.outputRole ?? 'main',
    aggRole: of.aggRole ?? '',
    defaultValue: formDefaultValue(of.defaultValue),
    // INT-1350 三轮：pass_threshold 反填回编辑框（不丢不置空）
    passThreshold: of.passThreshold != null ? String(of.passThreshold) : '',
    visibleInReport: of.visibleInReport === undefined ? true : !!of.visibleInReport,
    helpText: of.helpText ?? '',
    uiOrder: of.uiOrder ?? 0,
  }))
  const apiEndpoints = (dimension.apiEndpoints ?? []).map((ep) => ({
    url: ep.url ?? '',
    name: ep.name ?? '',
    priority: ep.priority ?? 1,
    maxProcess: ep.maxProcess ?? 5,
    maxTimeout: ep.maxTimeout ?? 30,
    maxAudioDuration: ep.maxAudioDuration ?? 60,
  }))
  return {
    name: dimension.name,
    description: dimension.description ?? '',
    evaluationType: dimension.type === 'manual' ? 'manual' : 'auto',
    categoryId: dimension.categoryId != null ? String(dimension.categoryId) : '',
    status: dimension.status ?? true,
    dimensionType: dimension.dimensionType === 'sub' ? 'sub' : 'main',
    parentDimensionId:
      dimension.parentDimensionId != null ? String(dimension.parentDimensionId) : '',
    keywords: dimension.keywords ?? '',
    scoreUnit: dimension.scoreUnit ?? '',
    resultType:
      dimension.resultType === 'llm_judge'
        ? 'llm_judge'
        : String(dimension.resultType ?? 1) as DimensionFormValues['resultType'],
    resultMin: dimension.resultMin ?? 0,
    resultMax: dimension.resultMax ?? 100,
    decimalPlaces: dimension.decimalPlaces ?? 2,
    weight: dimension.weight ?? 5,
    estimatedExecTime: dimension.estimatedExecTime ?? 5,
    rule: ruleRows.length > 0 ? ruleRows : emptyDimensionFormValues().rule,
    llmModel: dimension.llmJudgeConfig?.model ?? '',
    llmPromptTemplate: dimension.llmJudgeConfig?.promptTemplate ?? '',
    llmMaxTokens: dimension.llmJudgeConfig?.maxTokens ?? 1024,
    llmTemperature: dimension.llmJudgeConfig?.temperature ?? 0.7,
    apiUrl: dimension.apiUrl ?? '',
    apiMethod: toApiMethod(dimension.apiSettings),
    apiTimeout: toApiTimeout(dimension.apiSettings),
    apiHeaders: toApiHeaders(dimension.apiSettings),
    apiBodyTemplate: toApiBodyTemplate(dimension.apiSettings),
    statisticMethod: dimension.statisticMethod ?? 'average',
    aggDenominator: dimension.aggDenominator ?? 'case',
    excludeRounds: (dimension.excludeRounds ?? []).map(String),
    associatedAlgorithms: (dimension.associatedAlgorithms ?? []).map(
      (a) => a.algorithmType
    ),
    requiredInputs:
      requiredInputs.length > 0
        ? requiredInputs
        : emptyDimensionFormValues().requiredInputs,
    outputFields:
      outputFields.length > 0
        ? outputFields
        : emptyDimensionFormValues().outputFields,
    apiEndpoints:
      apiEndpoints.length > 0
        ? apiEndpoints
        : emptyDimensionFormValues().apiEndpoints,
  }
}

/** api_settings 读取辅助（编辑反填；宽对象安全读取） */
function toApiMethod(
  settings: Dimension['apiSettings']
): DimensionFormValues['apiMethod'] {
  if (
    settings &&
    typeof settings === 'object' &&
    typeof settings.method === 'string'
  ) {
    const method = settings.method
    if (
      method === 'GET' ||
      method === 'POST' ||
      method === 'PUT' ||
      method === 'DELETE' ||
      method === 'PATCH'
    )
      return method
  }
  return 'POST'
}

function toApiTimeout(settings: Dimension['apiSettings']): number {
  if (settings && typeof settings === 'object' && typeof settings.timeout === 'number')
    return settings.timeout
  return 30000
}

function toApiHeaders(settings: Dimension['apiSettings']): string {
  if (settings && typeof settings === 'object' && settings.headers)
    return JSON.stringify(settings.headers, null, 2)
  return ''
}

function toApiBodyTemplate(settings: Dimension['apiSettings']): string {
  if (settings && typeof settings === 'object' && settings.bodyTemplate != null)
    return JSON.stringify(settings.bodyTemplate, null, 2)
  return ''
}

/** 表单值 → 保存载荷（收敛为 Partial<Dimension>） */
export function toDimensionSaveInput(values: DimensionFormValues): Partial<Dimension> {
  const isSub = values.dimensionType === 'sub'
  return {
    name: values.name,
    description: values.description || null,
    type: values.evaluationType,
    categoryId: values.categoryId ? Number(values.categoryId) : null,
    status: values.status,
    dimensionType: values.dimensionType,
    parentDimensionId: isSub && values.parentDimensionId
      ? Number(values.parentDimensionId)
      : null,
    keywords: isSub ? null : values.keywords || null,
    scoreUnit: values.scoreUnit || null,
    resultType:
      values.resultType === 'llm_judge'
        ? 'llm_judge'
        : Number(values.resultType),
    resultMin: values.resultMin,
    resultMax: values.resultMax,
    decimalPlaces: values.decimalPlaces,
    weight: values.weight,
    estimatedExecTime: values.estimatedExecTime,
    rule: { rules: values.rule },
    statisticMethod: values.statisticMethod,
    aggDenominator: values.aggDenominator,
    excludeRounds: values.excludeRounds.map(Number),
    associatedAlgorithms: values.associatedAlgorithms.map((t) => ({
      algorithmType: t,
      isDefault: false,
      weight: values.weight,
    })),
    // P3-2：所需输入/输出字段/API 端点随保存载荷提交（子维度继承父维度，不携带）
    requiredInputs: isSub
      ? undefined
      : values.requiredInputs.map((ri) => ({
          paramCode: ri.paramCode,
          paramName: ri.paramName || ri.label,
          label: ri.label || ri.paramName,
          fieldType: ri.fieldType,
          required: ri.required,
          // INT-1350 三轮：default_value 按 field_type 解析类型（number→Number /
          // boolean→Boolean / json→JSON.parse；text/timestamp 原样），否则数值 0 等
          // 经表单 String()→字符串上送 → 后端 json.dumps('0') 落成字符串 "0"（语义漂移）
          defaultValue: parseDefaultValueByType(ri.defaultValue, ri.fieldType),
          helpText: ri.helpText || undefined,
          uiOrder: ri.uiOrder,
        })),
    outputFields: isSub
      ? undefined
      : values.outputFields.map((of) => ({
          paramCode: of.paramCode,
          paramName: of.paramName || of.label,
          label: of.label || of.paramName,
          fieldPath: of.fieldPath,
          fieldType: of.fieldType,
          outputRole: of.outputRole,
          aggRole: of.aggRole,
          defaultValue: parseDefaultValueByType(of.defaultValue, of.fieldType),
          passThreshold: toNullableNumber(of.passThreshold),
          visibleInReport: of.visibleInReport,
          helpText: of.helpText || undefined,
          uiOrder: of.uiOrder,
        })),
    apiEndpoints: isSub
      ? undefined
      : values.apiEndpoints.map((ep) => ({
          url: ep.url,
          name: ep.name,
          priority: ep.priority,
          maxProcess: ep.maxProcess,
          maxTimeout: ep.maxTimeout,
          maxAudioDuration: ep.maxAudioDuration,
        })),
    apiUrl: isSub ? null : values.apiUrl || null,
    apiSettings: isSub
      ? undefined
      : {
          method: values.apiMethod,
          timeout: values.apiTimeout,
          headers: values.apiHeaders
            ? (parseJsonObject(values.apiHeaders) as Record<string, string> | undefined)
            : undefined,
          bodyTemplate: values.apiBodyTemplate
            ? parseJsonValue(values.apiBodyTemplate)
            : undefined,
        },
    llmJudgeConfig:
      values.resultType === 'llm_judge'
        ? {
            model: values.llmModel,
            promptTemplate: values.llmPromptTemplate,
            maxTokens: values.llmMaxTokens,
            temperature: values.llmTemperature,
          }
        : null,
  }
}

/** JSON 字符串 → 对象（宽松解析，失败返回 undefined） */
function parseJsonObject(value: string): Record<string, unknown> | undefined {
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' ? parsed : undefined
  } catch {
    return undefined
  }
}

function parseJsonValue(value: string): unknown {
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}

/**
 * default_value 反填编辑表单（INT-1350 三轮，P2 配套）。
 * 对象/数组须 JSON.stringify（否则 String({k:1})='[object Object]'，保存时 JSON.parse 回不来）；
 * 数值/布尔按原值 String；null/undefined → ''。
 */
function formDefaultValue(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return ''
    }
  }
  return String(value)
}

/**
 * default_value 按 field_type 解析（INT-1350 三轮，P2）。
 * 表单默认值输入恒为字符串；保存时数值/布尔/JSON 型须还原为对应类型，
 * 否则后端 `json.dumps('0')` 会把数值 0 落成字符串 "0"（语义漂移）。
 * - number → Number（NaN 回退原字符串）
 * - boolean → 'true'/'1' → true；'false'/'0' → false；其余原样
 * - json → JSON.parse（失败回退原字符串）
 * - text / timestamp / audio → 原样
 * - 空 → undefined（键不上送 → 后端 default_value=None）
 */
function parseDefaultValueByType(value: string, fieldType: string): unknown {
  if (value === '') return undefined
  switch (fieldType) {
    case 'number': {
      const n = Number(value)
      return Number.isNaN(n) ? value : n
    }
    case 'boolean': {
      if (value === 'true' || value === '1') return true
      if (value === 'false' || value === '0') return false
      return value
    }
    case 'json':
      return parseJsonValue(value)
    default:
      return value
  }
}

/** 表单达标阈值字符串 → number | null（空 / 非法 → null） */
function toNullableNumber(value: string): number | null {
  if (value === '') return null
  const n = Number(value)
  return Number.isNaN(n) ? null : n
}

/** 分类图标占位（§5.5 分类表单默认） */
export const CATEGORY_ICON_PLACEHOLDER = DEFAULT_CATEGORY_ICON

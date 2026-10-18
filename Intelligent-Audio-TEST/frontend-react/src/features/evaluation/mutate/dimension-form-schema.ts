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

/** 所需输入配置行（API配置节「所需输入配置」编辑器行；对齐 DimensionRequiredInput） */
export interface RequiredInputRow {
  key: string
  label: string
  fieldType: string
  required: boolean
  defaultValue: string
  description: string
}

/** 输出字段配置行（API配置节「输出字段配置」编辑器行；对齐 DimensionOutputField） */
export interface OutputFieldRow {
  name: string
  label: string
  outputRole: string
  aggRole: string
  defaultValue: string
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
  key: z.string(),
  label: z.string(),
  fieldType: z.string(),
  required: z.boolean(),
  defaultValue: z.string(),
  description: z.string(),
})
const outputFieldRowSchema = z.object({
  name: z.string(),
  label: z.string(),
  outputRole: z.string(),
  aggRole: z.string(),
  defaultValue: z.string(),
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
    resultMin: z.number(),
    resultMax: z.number(),
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
        key: 'asr_result',
        label: 'ASR识别结果',
        fieldType: '文本',
        required: true,
        defaultValue: '',
        description: 'ASR算法识别出的文本',
      },
      {
        key: 'asr_ref',
        label: '参考文本',
        fieldType: '文本',
        required: true,
        defaultValue: '',
        description: '标准参考文本',
      },
    ],
    outputFields: [
      {
        name: 'score',
        label: '评分结果',
        outputRole: '主结果',
        aggRole: '直接值',
        defaultValue: '',
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
    key: ri.key ?? '',
    label: ri.label ?? '',
    fieldType: ri.fieldType ?? '文本',
    required: !!ri.required,
    defaultValue: ri.defaultValue != null ? String(ri.defaultValue) : '',
    description: ri.description ?? '',
  }))
  const outputFields = (dimension.outputFields ?? []).map((of) => ({
    name: of.name ?? '',
    label: of.label ?? '',
    outputRole: of.outputRole ?? '主结果',
    aggRole: of.aggRole ?? '直接值',
    defaultValue: of.defaultValue != null ? String(of.defaultValue) : '',
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

/** 表单值 → 保存载荷（收敛为 Partial<Dimension>；mock 阶段仅演示） */
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
          key: ri.key,
          label: ri.label,
          fieldType: ri.fieldType,
          required: ri.required,
          defaultValue: ri.defaultValue || undefined,
          description: ri.description || undefined,
        })),
    outputFields: isSub
      ? undefined
      : values.outputFields.map((of) => ({
          name: of.name,
          label: of.label,
          outputRole: of.outputRole,
          aggRole: of.aggRole,
          defaultValue: of.defaultValue || undefined,
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

/** 分类图标占位（§5.5 分类表单默认） */
export const CATEGORY_ICON_PLACEHOLDER = DEFAULT_CATEGORY_ICON

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

/** 规则行 zod 字段（与 RuleRow 同构） */
const ruleRowSchema = z.object({
  condition: z.string(),
  value: z.number(),
  score: z.number(),
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
    resultType: z.enum(['1', '2', '3', 'llm_judge']),
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

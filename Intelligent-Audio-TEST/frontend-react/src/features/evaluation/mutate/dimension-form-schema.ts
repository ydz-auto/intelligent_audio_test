/**
 * 评估维度表单 schema + 转换器（features/evaluation/mutate；11_用例域.md §5.5）。
 * 六分组节（基本信息/层级配置/结果配置/API配置/关联算法）字段常量与 RHF+zod schema；
 * 表单值类型由 schema 推导（DimensionFormValues），编辑态由 Dimension 反填、保存态
 * 收敛为 Partial<Dimension>。
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
 * rule 中除 `rules` 外的其余键（INT-1732）。
 * 后端把 rule 当不透明 JSON 原样落库（api_gateway DimensionInput.rule: Dict，命令侧无结构收口），
 * 真实库里 55/63 维度带 `defaultScore`。表单只编辑 rules 编辑器，其余键必须随保存原样带回，
 * 否则「打开编辑 → 不改字段 → 保存」会静默丢掉 defaultScore（P2）。
 */
type RuleExtra = Record<string, unknown>

/**
 * 所需输入配置行（API配置节「所需输入配置」编辑器行；对齐 DimensionRequiredInput：
 * paramCode / paramName / fieldType / required / defaultValue / helpText / uiOrder）。
 * INT-1690：编辑器只有「显示标签」一个可见口径（绑定 paramName），旧隐藏 label 字段
 * 会在保存时压过可见值，已移除；落库时 param_name / label 同取 paramName。
 */
export interface RequiredInputRow {
  paramCode: string
  paramName: string
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
 * paramCode / paramName / fieldPath / fieldType / outputRole / aggRole /
 * defaultValue / passThreshold / visibleInReport / helpText / uiOrder）。
 * INT-1690：同输入行，隐藏 label 字段移除，paramName 为唯一可见口径。
 */
export interface OutputFieldRow {
  paramCode: string
  paramName: string
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
  fieldType: z.string(),
  required: z.boolean(),
  defaultValue: z.string(),
  helpText: z.string(),
  uiOrder: z.number(),
})
const outputFieldRowSchema = z.object({
  paramCode: z.string(),
  paramName: z.string(),
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
    // 结果类型只有整数口径（网关 schemas/evaluation.py 是 int）；LLM Judge 由维度
    // 自身 task_type_code 表达，不再是结果类型选项（INT-1681 / INT-1671 裁定 A）
    resultType: z.enum(['0', '1', '2', '3']),
    // valueAsNumber 下清空输入得 NaN，默认文案是英文（Invalid input: expected number…）；
    // 给中文文案，行内错误/页脚摘要才可读（INT-1551）
    resultMin: z.number({ error: '结果最小值请输入数字' }),
    resultMax: z.number({ error: '结果最大值请输入数字' }),
    decimalPlaces: z.number().min(0).max(4, '小数位数 0-4'),
    weight: z.number().min(WEIGHT_MIN).max(WEIGHT_MAX, '权重 1-10'),
    estimatedExecTime: z.number().min(1, '预计执行时间 ≥1 秒'),
    // INT-1732：评分规则可空（真实库 55/63 维度 rules=[]），不再强制至少 1 条
    rule: z.array(ruleRowSchema),
    /** rule 中除 rules 外的其余键（defaultScore 等），保存时原样带回 */
    ruleExtra: z.record(z.string(), z.unknown()),
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
    // 默认 6 条规则只用于新建（编辑反填不再兜底，见 toDimensionFormValues INT-1732）；
    // 档位对齐 V9.7.10 dimensionTemplate.rule（>=60→6 / <60→0，INT-1816 P3-2）
    rule: [
      { condition: '>=', value: 95, score: 10 },
      { condition: '>=', value: 90, score: 9 },
      { condition: '>=', value: 80, score: 8 },
      { condition: '>=', value: 70, score: 7 },
      { condition: '>=', value: 60, score: 6 },
      { condition: '<', value: 60, score: 0 },
    ],
    ruleExtra: {},
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
        fieldType: 'text',
        required: true,
        defaultValue: '',
        helpText: 'ASR算法识别出的文本',
        uiOrder: 1,
      },
      {
        paramCode: 'asr_ref',
        paramName: '参考文本',
        fieldType: 'text',
        required: true,
        defaultValue: '',
        helpText: '标准参考文本',
        uiOrder: 2,
      },
    ],
    // INT-1816 P3-1：V9.7.10 newDimension 不带输出字段，新建不预填示例（score/评分结果）；
    // 只填名称直接保存不再凭空落一条假输出字段
    outputFields: [],
    apiEndpoints: [
      // INT-1732 P3-3：V9.7.10 新建端点 URL 为空（此前预填 api.example.com 示例地址，
      // 不改直接保存就落一条假端点）
      {
        url: '',
        name: '',
        priority: 1,
        maxProcess: 5,
        maxTimeout: 30,
        maxAudioDuration: 60,
      },
    ],
  }
}

/**
 * rule 归一为普通对象（INT-1732）。
 * - 对象：浅拷贝（含 rules 与 defaultScore 等）
 * - JSON 字符串（历史数据）：解析，失败按空对象
 * - 数组（更早的 rule 直接是规则列表）：包成 { rules }
 * - null/其它：空对象
 */
function parseRuleObject(rule: Dimension['rule']): RuleExtra {
  if (rule == null) return {}
  if (Array.isArray(rule)) return { rules: rule }
  if (typeof rule === 'string') {
    try {
      const parsed: unknown = JSON.parse(rule)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return { ...(parsed as RuleExtra) }
      }
      if (Array.isArray(parsed)) return { rules: parsed }
    } catch {
      return {}
    }
    return {}
  }
  return typeof rule === 'object' ? { ...rule } : {}
}

/** 编辑态 Dimension → 表单值（反填） */
export function toDimensionFormValues(dimension: Dimension): DimensionFormValues {
  // INT-1732：rule 是后端不透明 JSON（可能是对象，历史数据也可能是 JSON 字符串）。
  // 解析成对象后拆两半：rules 进规则编辑器，其余键（defaultScore 等）进 ruleExtra 原样带回。
  const { rules: parsedRules, ...ruleExtra } = parseRuleObject(dimension.rule)
  const ruleRows: RuleRow[] = (Array.isArray(parsedRules) ? parsedRules : [])
    .filter((r): r is Record<string, unknown> => Boolean(r) && typeof r === 'object')
    .map((r) => ({
      condition: String(r.condition),
      value: Number(r.value),
      score: Number(r.score),
    }))
  // 子编辑器反填（P3-2）：缺省（null/空）时回退默认行，保证编辑态可继续编辑
  // INT-1690：显示标签只有 paramName 一个口径；旧数据 param_name 缺失时仍可用 label 兜底回显
  const requiredInputs = (dimension.requiredInputs ?? []).map((ri) => ({
    paramCode: ri.paramCode ?? '',
    paramName: ri.paramName || ri.label || '',
    fieldType: ri.fieldType ?? 'text',
    required: ri.required === undefined ? true : !!ri.required,
    defaultValue: formDefaultValue(ri.defaultValue),
    helpText: ri.helpText ?? '',
    uiOrder: ri.uiOrder ?? 0,
  }))
  const outputFields = (dimension.outputFields ?? []).map((of) => ({
    paramCode: of.paramCode ?? '',
    paramName: of.paramName || of.label || '',
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
    // INT-1671 裁定 A：LLM Judge 由后端派生布尔表达，结果类型仍是数值/布尔/文本的整数
    resultType: String(dimension.resultType ?? 1) as DimensionFormValues['resultType'],
    resultMin: dimension.resultMin ?? 0,
    resultMax: dimension.resultMax ?? 100,
    decimalPlaces: dimension.decimalPlaces ?? 2,
    weight: dimension.weight ?? 5,
    estimatedExecTime: dimension.estimatedExecTime ?? 5,
    // INT-1732：空规则就空着（不再用默认 5 条兜底——那会让真实维度凭空出现规则、保存即覆盖）
    rule: ruleRows,
    ruleExtra,
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
    // INT-1816 P3-1：空就空着（不兜底默认输出字段——否则没有输出字段的维度会凭空
    // 出现示例 score 行，保存即落库）
    outputFields,
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
    // 只发整数（后端 result_type 是 int）；LLM Judge 是维度属性，不写结果类型（INT-1681 / INT-1671 裁定 A）
    resultType: Number(values.resultType),
    resultMin: values.resultMin,
    resultMax: values.resultMax,
    decimalPlaces: values.decimalPlaces,
    weight: values.weight,
    estimatedExecTime: values.estimatedExecTime,
    // INT-1732：rules 以编辑器为准，rule 其余键（defaultScore 等）原样保留；
    // 空规则维度原样保存后 rule 仍是 { rules: [], defaultScore }，不再被默认模板覆盖
    rule: { ...values.ruleExtra, rules: values.rule },
    statisticMethod: values.statisticMethod,
    aggDenominator: values.aggDenominator,
    excludeRounds: values.excludeRounds.map(Number),
    associatedAlgorithms: values.associatedAlgorithms.map((t) => ({
      algorithmType: t,
      isDefault: false,
      weight: values.weight,
    })),
    // P3-2：所需输入/输出字段/API 端点随保存载荷提交（子维度继承父维度，不携带）
    // INT-1690：param_name / label 同取可见的 paramName —— 旧隐藏 label 会把编辑掉的
    // 「输入显示标签」用旧值覆盖，后端又按 param_name 优先，导致编辑不落库。
    requiredInputs: isSub
      ? undefined
      : values.requiredInputs.map((ri) => ({
          paramCode: ri.paramCode,
          paramName: ri.paramName,
          label: ri.paramName,
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
          paramName: of.paramName,
          label: of.paramName,
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
    // INT-1671 裁定 A：不再写 llmJudgeConfig（历史数据后端保持原值，前端不删不清）
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

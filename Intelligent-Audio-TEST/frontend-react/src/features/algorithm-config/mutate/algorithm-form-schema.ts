/**
 * §6 算法编辑表单 zod schema（features/algorithm-config/mutate）。
 * INT-591 §6.2 双门槛：
 * - 草稿保存 = 宽松结构级校验（algorithmDraftFormSchema）：仅参数代码非空、同作用域唯一；
 *   算法代码/名称/分组等允许暂存未完备内容（草稿是中间态）。
 * - 发布 = 严格全量校验（algorithmFormSchema / algorithmEditFormSchema）：结构级 +
 *   算法代码正则（新建态）、名称/分组必填、范围 min≤max、类型合法。
 * RHF 值类型见 features/algorithm-config/types.ts（AlgorithmFormValues）。
 *
 * 算法代码（type）分两档（发布态）：
 * - 新建态（algorithmFormSchema）：走 §6.2 新建正则 ^[a-z][a-z0-9_]*$；
 * - 编辑/复制态（algorithmEditFormSchema）：代码为主键、字段禁用不可改，
 *   仅必填+长度（对齐 api_gateway/schemas/_algorithm_definition_schemas.py
 *   `type: Field(min_length=1, max_length=50)`，存量代码含连字符如 asr-v3）。
 */
import { z } from 'zod'

/** 算法代码正则（§6.2 新建校验 ^[a-z][a-z0-9_]*$） */
export const ALGORITHM_TYPE_PATTERN = /^[a-z][a-z0-9_]*$/

/**
 * 参数代码字段（§6.2 双门槛）：
 * - 发布（enforcePattern=true）= 正则（小写字母开头），设备/API/用例参数行级；
 * - 草稿（enforcePattern=false）= 仅非空（正则草稿阶段不校验，草稿是中间态允许暂存未完备内容）。
 */
function paramCodeField(enforcePattern: boolean) {
  const base = z.string().min(1, '参数代码不能为空')
  return enforcePattern
    ? base.regex(ALGORITHM_TYPE_PATTERN, '参数代码需小写字母开头')
    : base
}

/**
 * 参数类型字段（§6.2 双门槛）：
 * - 发布（enforceRequired=true）= 必填（「请选择参数类型」）；
 * - 草稿（enforceRequired=false）= 可暂缺（类型草稿阶段不校验，允许暂存未完备内容）。
 */
function paramTypeField(enforceRequired: boolean) {
  const base = z.string()
  return enforceRequired ? base.min(1, '请选择参数类型') : base
}

/** 算法代码字段：新建态走 §6.2 正则；编辑/复制态仅必填+长度（后端契约 min 1 / max 50） */
function algorithmTypeField(enforcePattern: boolean) {
  const base = z.string().min(1, '算法代码不能为空').max(50, '算法代码过长')
  return enforcePattern
    ? base.regex(ALGORITHM_TYPE_PATTERN, '算法代码需小写字母开头')
    : base
}

/** 映射行 schema（§6.5 设备/API/评估三节共用；INT-1160 返工字段补齐，可选字段 output 与 MappingRow 对齐） */
function mappingRowSchema(sourceRequired: boolean, targetRequired: boolean) {
  return z.object({
    key: z.string(),
    id: z.number().optional(),
    source: z.string().optional(),
    sourceDirection: z.string().optional(),
    sourceParam: sourceRequired ? z.string().min(1, '请选择源参数') : z.string(),
    paramName: z.string().optional(),
    dimensionId: z.string().optional(),
    dimensionName: z.string().optional(),
    targetParam: targetRequired ? z.string().min(1, '请选择目标参数') : z.string(),
    targetParamName: z.string().optional(),
    transformType: z.string(),
  })
}

const baseObjectFields = {
  type: z.string(),
  name: z.string(),
  groupId: z.string(),
  displayOrder: z.number().min(0, '排序不能为负'),
  status: z.enum(['online', 'offline']),
  description: z.string(),

  deviceParams: z.array(
    z.object({
      key: z.string(),
      paramCode: paramCodeField(true),
      paramName: z.string(),
      direction: z.enum(['input', 'output']),
      paramType: paramTypeField(true),
      required: z.boolean(),
      defaultValue: z.string(),
      helpText: z.string(),
    })
  ),
  apiParams: z.array(
    z.object({
      key: z.string(),
      paramCode: paramCodeField(true),
      paramName: z.string(),
      direction: z.enum(['input', 'output']),
      paramType: paramTypeField(true),
      required: z.boolean(),
      defaultValue: z.string(),
      helpText: z.string(),
    })
  ),
  caseParams: z.array(
    z.object({
      key: z.string(),
      paramCode: paramCodeField(true),
      paramName: z.string(),
      paramType: paramTypeField(true),
      scope: z.enum(['common', 'api', 'e2e']),
      required: z.boolean(),
      defaultValue: z.string(),
      minValue: z.string(),
      maxValue: z.string(),
      step: z.string(),
      unit: z.string(),
      annotationCode: z.string(),
      fieldPath: z.string(),
      helpText: z.string(),
    })
  ),
  referenceParams: z.array(
    z.object({
      key: z.string(),
      code: z.string().min(1, '参数代码不能为空'),
      name: z.string(),
      type: z.string().min(1, '请选择参考类型'),
      annotationCode: z.string(),
      annotationFormat: z.string(),
      fieldPath: z.string(),
      mergeMode: z.string(),
      helpText: z.string(),
    })
  ),
  mappings: z.object({
    device: z.array(mappingRowSchema(true, true)),
    api: z.array(mappingRowSchema(true, true)),
    evaluation: z.array(mappingRowSchema(true, true)),
  }),
  associatedDimensions: z.array(
    z.object({
      key: z.string(),
      dimensionId: z.string().min(1, '请选择评估维度'),
      dimensionName: z.string(),
      weight: z.string(),
      isDefault: z.boolean(),
    })
  ),
}

/**
 * 草稿宽松字段集（§6.2 结构级门槛：仅参数代码非空 + 同作用域唯一）。
 * 在严格字段集（baseObjectFields）基础上仅放宽：参数代码去正则、
 * 参数类型/参考类型/映射源目/维度去非空——草稿是中间态，允许暂存未完备内容；
 * 发布 schema（buildPublishAlgorithmFormSchema）另行保持严格双门槛。
 */
const draftObjectFields = {
  ...baseObjectFields,
  deviceParams: z.array(
    z.object({
      ...baseObjectFields.deviceParams.element.shape,
      paramCode: paramCodeField(false),
      paramType: paramTypeField(false),
    })
  ),
  apiParams: z.array(
    z.object({
      ...baseObjectFields.apiParams.element.shape,
      paramCode: paramCodeField(false),
      paramType: paramTypeField(false),
    })
  ),
  caseParams: z.array(
    z.object({
      ...baseObjectFields.caseParams.element.shape,
      paramCode: paramCodeField(false),
      paramType: paramTypeField(false),
    })
  ),
  referenceParams: z.array(
    z.object({
      ...baseObjectFields.referenceParams.element.shape,
      type: z.string(), // 参考类型草稿阶段不校验（发布严格门）
    })
  ),
  mappings: z.object({
    device: z.array(mappingRowSchema(false, false)),
    api: z.array(mappingRowSchema(false, false)),
    evaluation: z.array(mappingRowSchema(false, false)),
  }),
  associatedDimensions: z.array(
    z.object({
      ...baseObjectFields.associatedDimensions.element.shape,
      dimensionId: z.string(), // 维度草稿阶段不校验（发布严格门）
    })
  ),
}

/**
 * 草稿宽松 schema（§6.2 结构级门槛）：仅参数代码非空 + 同作用域唯一。
 * 算法代码/名称/分组/参数类型/映射/维度等可空或未完备（草稿是中间态，允许暂存），
 * 正则/类型/范围等发布严格门槛草稿阶段不校验。
 */
export const algorithmDraftFormSchema = z
  .object({ ...draftObjectFields })
  .superRefine((values, ctx) => {
    // 同作用域内参数代码唯一（§6.4：统一表行带 scope 标记，唯一性按 device/api/case 各数组）
    checkUnique(ctx, 'deviceParams', 'paramCode', values.deviceParams.map((p) => p.paramCode))
    checkUnique(ctx, 'apiParams', 'paramCode', values.apiParams.map((p) => p.paramCode))
    checkUnique(ctx, 'caseParams', 'paramCode', values.caseParams.map((p) => p.paramCode))
    checkUnique(ctx, 'referenceParams', 'code', values.referenceParams.map((p) => p.code))
  })

/**
 * 发布严格 schema（§6.2 全量门槛）。enforcePattern=新建态（算法代码正则）、
 * 编辑/复制态代码为主键仅必填+长度。范围 min≤max 行级校验（number/slider）。
 */
function buildPublishAlgorithmFormSchema(enforcePattern: boolean) {
  return z
    .object({
      ...baseObjectFields,
      type: algorithmTypeField(enforcePattern),
      name: z.string().min(1, '显示名称不能为空'),
      // 所属分组可空（V9.7.10 行为：group_id 允许 null；后端 AlgorithmDefinitionCreate.group_id
      // Optional，存量 voice_llm 即未分组；空串在 save 侧映射为 group_id null）
      groupId: z.string(),
    })
    .superRefine((values, ctx) => {
      // 参数代码同作用域唯一（§6.4）
      checkUnique(ctx, 'deviceParams', 'paramCode', values.deviceParams.map((p) => p.paramCode))
      checkUnique(ctx, 'apiParams', 'paramCode', values.apiParams.map((p) => p.paramCode))
      checkUnique(ctx, 'caseParams', 'paramCode', values.caseParams.map((p) => p.paramCode))
      checkUnique(ctx, 'referenceParams', 'code', values.referenceParams.map((p) => p.code))
      // 范围 min≤max（number/slider 型；发布严格门槛，草稿不校验）
      checkRange(ctx, values.caseParams)
      // 参数映射判重兜底（§6.5/INT-1160 返工）：与后端 _upsert_mappings 唯一约束对齐
      checkMappingDuplicates(ctx, values.mappings)
    })
}

/** 新建发布 schema（§6.2：算法代码走新建正则） */
export const algorithmFormSchema = buildPublishAlgorithmFormSchema(true)

/** 编辑/复制发布 schema（算法代码为主键禁用不可改，仅必填+长度，对齐后端契约） */
export const algorithmEditFormSchema = buildPublishAlgorithmFormSchema(false)

function checkUnique(
  ctx: z.RefinementCtx,
  field: 'deviceParams' | 'apiParams' | 'caseParams' | 'referenceParams',
  subField: 'paramCode' | 'code',
  codes: string[]
) {
  const seen = new Set<string>()
  codes.forEach((code, index) => {
    const normalized = code.trim()
    if (!normalized) return
    if (seen.has(normalized)) {
      ctx.addIssue({
        code: 'custom',
        path: [field, index, subField],
        message: '参数代码重复',
      })
    }
    seen.add(normalized)
  })
}

/** 范围 min≤max 行级校验（§6.6 发布严格；number/slider 且 min/max 均已填时比较） */
function checkRange(
  ctx: z.RefinementCtx,
  caseParams: Array<{
    paramType: string
    minValue: string
    maxValue: string
  }>
) {
  caseParams.forEach((param, index) => {
    if (param.paramType !== 'number' && param.paramType !== 'slider') return
    if (param.minValue === '' || param.maxValue === '') return
    const min = Number(param.minValue)
    const max = Number(param.maxValue)
    if (Number.isNaN(min) || Number.isNaN(max)) return
    if (min > max) {
      ctx.addIssue({
        code: 'custom',
        path: ['caseParams', index, 'minValue'],
        message: '最小值不能大于最大值',
      })
      ctx.addIssue({
        code: 'custom',
        path: ['caseParams', index, 'maxValue'],
        message: '最大值不能小于最小值',
      })
    }
  })
}

type MappingRowDupShape = {
  source?: string
  sourceParam: string
  dimensionId?: string
}

/**
 * 参数映射判重兜底（§6.5/INT-1160 返工）：与后端 `_upsert_mappings` 唯一约束
 * (source, source_param, dimension_id) 对齐。
 * - 设备/API 来源 = 节类型固定，唯一键 = 源参数代码（dimension_id 恒空）；
 * - 评估 唯一键 = (来源, 源参数代码, 维度)。
 * 发布严格门槛（草稿宽松 schema 不校验）；行内 handler 实时判重弹 toast，
 * 此处兜底把重复行挡在发布之外（防后端 find-or-upsert 静默合并覆盖）。
 */
function checkMappingDuplicates(
  ctx: z.RefinementCtx,
  mappings: {
    device: MappingRowDupShape[]
    api: MappingRowDupShape[]
    evaluation: MappingRowDupShape[]
  }
) {
  const seenSection = (section: 'device' | 'api' | 'evaluation') => {
    const rows = mappings[section]
    const seen = new Map<string, number>()
    rows.forEach((row, index) => {
      if (!row.sourceParam) return
      const key =
        section === 'evaluation'
          ? `${row.source || 'case'}\u0000${row.sourceParam}\u0000${row.dimensionId || ''}`
          : row.sourceParam
      if (seen.has(key)) {
        ctx.addIssue({
          code: 'custom',
          path: ['mappings', section, index, 'sourceParam'],
          message: '映射重复：同一来源+源参数+维度不允许重复',
        })
      }
      seen.set(key, index)
    })
  }
  seenSection('device')
  seenSection('api')
  seenSection('evaluation')
}

export type AlgorithmFormSchema = z.infer<typeof algorithmFormSchema>

/**
 * §6 算法编辑表单 zod schema（features/algorithm-config/mutate）。
 * 基本信息必填校验 + 参数代码唯一性（同页签内）行级校验；范围 min≤max 行级校验。
 * RHF 值类型见 features/algorithm-config/types.ts（AlgorithmFormValues）。
 */
import { z } from 'zod'

/** 算法代码正则（§6.2 新建校验 ^[a-z][a-z0-9_]*$，编辑/复制态 disabled 为主键） */
export const ALGORITHM_TYPE_PATTERN = /^[a-z][a-z0-9_]*$/

/** 参数代码（同页签内唯一，行级） */
function paramCodeField() {
  return z
    .string()
    .min(1, '参数代码不能为空')
    .regex(ALGORITHM_TYPE_PATTERN, '参数代码需小写字母开头')
}

export const algorithmFormSchema = z
  .object({
    type: z
      .string()
      .min(1, '算法代码不能为空')
      .regex(ALGORITHM_TYPE_PATTERN, '算法代码需小写字母开头'),
    name: z.string().min(1, '显示名称不能为空'),
    groupId: z.string().min(1, '请选择所属分组'),
    displayOrder: z.number().min(0, '排序不能为负'),
    status: z.enum(['online', 'offline']),
    description: z.string(),

    deviceParams: z.array(
      z.object({
        key: z.string(),
        paramCode: paramCodeField(),
        paramName: z.string(),
        direction: z.enum(['input', 'output']),
        paramType: z.string().min(1, '请选择参数类型'),
        required: z.boolean(),
        helpText: z.string(),
      })
    ),
    apiParams: z.array(
      z.object({
        key: z.string(),
        paramCode: paramCodeField(),
        paramName: z.string(),
        direction: z.enum(['input', 'output']),
        paramType: z.string().min(1, '请选择参数类型'),
        required: z.boolean(),
        helpText: z.string(),
      })
    ),
    caseParams: z.array(
      z.object({
        key: z.string(),
        paramCode: paramCodeField(),
        paramName: z.string(),
        paramType: z.string().min(1, '请选择参数类型'),
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
      device: z.array(
        z.object({
          key: z.string(),
          sourceParam: z.string().min(1, '请选择源参数'),
          targetParam: z.string().min(1, '请选择目标参数'),
          transformType: z.string().min(1),
        })
      ),
      api: z.array(
        z.object({
          key: z.string(),
          sourceParam: z.string().min(1, '请选择源参数'),
          targetParam: z.string().min(1, '请选择目标参数'),
          transformType: z.string().min(1),
        })
      ),
      evaluation: z.array(
        z.object({
          key: z.string(),
          sourceParam: z.string().min(1, '请选择源参数'),
          targetParam: z.string().min(1, '请选择目标参数'),
          transformType: z.string().min(1),
        })
      ),
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
  })
  .superRefine((values, ctx) => {
    // 参数代码同页签唯一（§6.3 行级校验）
    checkUnique(ctx, 'deviceParams', 'paramCode', values.deviceParams.map((p) => p.paramCode))
    checkUnique(ctx, 'apiParams', 'paramCode', values.apiParams.map((p) => p.paramCode))
    checkUnique(ctx, 'caseParams', 'paramCode', values.caseParams.map((p) => p.paramCode))
    checkUnique(ctx, 'referenceParams', 'code', values.referenceParams.map((p) => p.code))
  })

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

export type AlgorithmFormSchema = z.infer<typeof algorithmFormSchema>

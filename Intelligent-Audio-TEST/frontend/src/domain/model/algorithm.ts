/**
 * Algorithm（算法配置）领域模型 —— camelCase
 * 对应后端 api_gateway/schemas/algorithm.py 与
 * task_service/application/algorithm/algorithm_crud_service.py 的序列化输出
 *
 * 枚举值保持后端原值，只转字段名。
 */

// ===== 算法定义 =====

/** 设备/API 参数项（对应 AlgorithmDeviceParamItem） */
export interface AlgorithmDeviceParam {
  id: number
  algorithmType: string
  paramCode: string
  paramName?: string
  label?: string
  paramType: string
  direction?: 'input' | 'output' | (string & {})
  required?: boolean
  defaultValue?: unknown
  optionsSource?: string
  optionsField?: string
  optionsLabelField?: string
  helpText?: string
  uiOrder?: number
  hidden?: boolean
}

/** 用例专属参数项（对应 CaseAlgorithmParam） */
export interface AlgorithmCaseParam {
  id: number
  algorithmType: string
  paramCode: string
  paramName?: string
  label?: string
  paramType?: string
  required?: boolean
  defaultValue?: unknown
  helpText?: string
  uiOrder?: number
  hidden?: boolean
  /** 参数作用域：common / round（后端原值） */
  scope?: string
  minValue?: number
  maxValue?: number
  step?: number
  unit?: string
}

/** 参数列表（list_params / list_case_params 返回） */
export interface AlgorithmParamList {
  parameters: AlgorithmDeviceParam[]
  total: number
}

/** 参数映射项（对应 list_mappings 的 mappings 列表项） */
export interface ParamMapping {
  id: number
  algorithmType: string
  /** 映射来源：device / api / evaluation（后端原值） */
  source: string
  sourceParam: string
  sourceDirection: string
  dimensionId?: number
  dimensionName?: string
  targetParam: string
  transformType: string
}

/** 算法分组（对应 AlgorithmGroupItem） */
export interface AlgorithmGroup {
  id: number
  name: string
  description?: string
  icon?: string
  displayOrder: number
  algorithmCount: number
  createdAt?: string
  updatedAt?: string
}

/** 算法选项（下拉列表项，对应 get_algorithm_options） */
export interface AlgorithmOption {
  value: string
  name: string
  groupId?: number
  groupName?: string
  icon?: string
}

/** 算法-维度关联维度项 */
export interface AlgorithmAssociatedDimension {
  id: number
  /** 关联的评估维度 id（后端字段 dimension_id） */
  dimensionId: number
  name: string
  description?: string
  type?: string
  weight: number
  isDefault: boolean
}

/** 算法-维度关联（对应 get_algorithm_dimensions） */
export interface AlgorithmDimensions {
  dimensions: AlgorithmAssociatedDimension[]
  dimensionIds: number[]
  defaultDimensionId: number | null
  weights: Record<number, number>
}

/** 维度参数项（对应 get_dimension_params） */
export interface DimensionParam {
  id: number
  dimensionId: number
  code: string
  name?: string
  label?: string
  fieldType: string
  paramDirection?: string
  fieldPath?: string
  aggRole?: string
  outputRole?: string
  visibleInReport?: boolean
  required?: boolean
  defaultValue?: unknown
  helpText?: string
  uiOrder?: number
}

// ===== 表单 Schema =====

/** 字段校验规则对象（form-schema 接口 validation 字段的对象形态） */
export interface FieldValidation {
  min?: number
  max?: number
  step?: number
  pattern?: string
  patternMessage?: string
  minLength?: number
  maxLength?: number
}

/** 表单字段（后端 form-schema 接口直接输出 camelCase） */
export interface FormField {
  fieldCode: string
  fieldName: string
  fieldType: string
  required: boolean
  defaultValue?: unknown
  component?: string
  options?: Array<{ value: string; label: string }>
  /** 校验规则：正则字符串（旧格式）或结构化对象（min/max/step/pattern 等） */
  validation?: string | FieldValidation
  helpText?: string
  hidden?: boolean
  uiOrder?: number
  uiGroup?: string
  scope?: string
}

/** 收窄取字段校验规则对象：validation 为字符串（旧正则格式）时返回 undefined */
export function getFieldValidation(field: Pick<FormField, 'validation'>): FieldValidation | undefined {
  return typeof field.validation === 'object' && field.validation !== null ? field.validation : undefined
}

/** 表单字段组 */
export interface FormFieldGroup {
  name: string
  label: string
  fields: FormField[]
}

/** 动态表单 Schema（对应 get_form_schema） */
export interface FormSchema {
  algorithmType: string
  algorithmName: string
  category?: string
  description?: string
  groups: FormFieldGroup[]
  fields: FormField[]
}

// ===== 操作结果 =====

/** 重载配置结果（对应 ReloadConfigResponse） */
export interface ReloadConfigResult {
  success: boolean
  message: string
  reloadTime?: string
}

/** 导入结果 */
export interface AlgorithmImportResult {
  imported: string[]
}

/** 批量删除结果 */
export interface AlgorithmBulkDeleteResult {
  deletedTypes: string[]
}

// ===== 参考参数 =====

/** 参考参数（对应 ReferenceParam） */
export interface ReferenceParam {
  id?: number
  code: string
  name: string
  type?: string
  helpText?: string
  algorithmType?: string
  annotationCode?: string
  annotationFormat?: string
  fieldPath?: string
  mergeMode?: string
}

// ===== 算法定义（聚合形状） =====

/** 算法定义（对应 AlgorithmDetailResponse） */
export interface AlgorithmDefinition {
  id: number
  type: string
  name: string
  groupId?: number
  groupName?: string
  category?: string
  description?: string
  status?: string
  icon?: string
  displayOrder: number
  deviceParams?: AlgorithmDeviceParam[]
  apiParams?: AlgorithmDeviceParam[]
  caseParams?: AlgorithmCaseParam[]
  /** 兼容字段：device_params 别名（微服务同时输出 params） */
  params?: AlgorithmDeviceParam[]
  /** 参数映射（按 source 分组：device / api / evaluation） */
  mappings?: Record<string, ParamMapping[]>
  /** 参考参数（前端本地字段；adapter 经 reference_params 出入口） */
  referenceParams?: ReferenceParam[]
  associatedDimensions?: AlgorithmAssociatedDimension[]
  dimensionRelations?: unknown[]
  createdAt?: string
  updatedAt?: string
}

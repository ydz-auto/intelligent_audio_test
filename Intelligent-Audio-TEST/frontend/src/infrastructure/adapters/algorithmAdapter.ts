/**
 * Algorithm Adapter —— DTO(snake_case) → Domain(camelCase)
 *
 * 后端契约：api_gateway/schemas/algorithm.py +
 * task_service/application/algorithm/* 的序列化输出。
 * 本文件是 algorithm 相关接口唯一允许做 snake_case → camelCase 键名转换的地方。
 */
import type {
  AlgorithmDefinitionDto,
  AlgorithmListDto,
  AlgorithmDeviceParamDto,
  AlgorithmCaseParamDto,
  AlgorithmParamListDto,
  ParamMappingDto,
  ParamMappingListDto,
  AlgorithmGroupDto,
  AlgorithmGroupListDto,
  AlgorithmOptionDto,
  AlgorithmDimensionsDto,
  DimensionParamDto,
  DimensionParamsResultDto,
  AlgorithmFormSchemaDto,
  ReloadConfigDto,
  AlgorithmImportResultDto,
  AlgorithmBulkDeleteResultDto,
  AlgorithmReferenceParamDto,
} from '../dto/algorithmDto'
import type {
  AlgorithmDefinition,
  AlgorithmDeviceParam,
  AlgorithmCaseParam,
  AlgorithmParamList,
  ParamMapping,
  AlgorithmGroup,
  AlgorithmOption,
  AlgorithmDimensions,
  AlgorithmAssociatedDimension,
  DimensionParam,
  FormSchema,
  FormFieldGroup,
  FormField,
  ReloadConfigResult,
  AlgorithmImportResult,
  AlgorithmBulkDeleteResult,
  ReferenceParam,
} from '../../domain/model/algorithm'
import { ApiEndpointStatus } from '../../domain/enums'

// ===== 算法定义 =====

/** AlgorithmDefinitionDto → AlgorithmDefinition（逐字段显式映射，可选缺失用 ?.） */
export function toAlgorithmDefinition(dto: AlgorithmDefinitionDto): AlgorithmDefinition {
  return {
    id: dto?.id ?? '',
    type: dto?.type ?? '',
    name: dto?.name ?? '',
    groupId: dto?.group_id,
    groupName: dto?.group_name,
    category: dto?.category,
    description: dto?.description,
    status: (dto?.status ?? ApiEndpointStatus.ONLINE) as AlgorithmDefinition['status'],
    icon: dto?.icon,
    displayOrder: dto?.display_order ?? 0,
    deviceParams: (dto?.device_params ?? []).map(toAlgorithmDeviceParamFromRaw),
    apiParams: (dto?.api_params ?? []).map(toAlgorithmDeviceParamFromRaw),
    caseParams: (dto?.case_params ?? []).map(toAlgorithmCaseParamFromRaw),
    params: (dto?.params ?? []).map(toAlgorithmDeviceParamFromRaw),
    mappings: dto?.mappings
      ? Object.fromEntries(
          Object.entries(dto.mappings).map(([k, list]) => [k, (list ?? []).map(toParamMappingFromRaw)])
        )
      : undefined,
    associatedDimensions: (dto?.associated_dimensions ?? []).map(toAlgorithmAssociatedDimensionFromRaw),
    dimensionRelations: dto?.dimension_relations,
    referenceParams: (dto?.reference_params ?? []).map(toReferenceParam),
    createdAt: dto?.created_at,
    updatedAt: dto?.updated_at,
  }
}

/** 算法定义列表（{ data, total }） */
export function toAlgorithmDefinitionList(dto: AlgorithmListDto | null | undefined): AlgorithmDefinition[] {
  return (dto?.data ?? []).map(toAlgorithmDefinition)
}

// ===== 参数 =====

/** AlgorithmDeviceParamDto → AlgorithmDeviceParam */
export function toAlgorithmDeviceParam(dto: AlgorithmDeviceParamDto): AlgorithmDeviceParam {
  return {
    id: dto?.id ?? 0,
    algorithmType: dto?.algorithm_type ?? '',
    paramCode: dto?.param_code ?? '',
    paramName: dto?.param_name,
    label: dto?.label,
    paramType: dto?.param_type ?? 'text',
    direction: (dto?.direction ?? 'input') as AlgorithmDeviceParam['direction'],
    required: dto?.required ?? false,
    defaultValue: dto?.default_value,
    optionsSource: dto?.options_source,
    optionsField: dto?.options_field,
    optionsLabelField: dto?.options_label_field,
    helpText: dto?.help_text,
    uiOrder: dto?.ui_order ?? 0,
    hidden: dto?.hidden ?? false,
  }
}

/** 后端宽松对象 → 设备/API 参数 Domain（definition 内嵌列表项） */
export function toAlgorithmDeviceParamFromRaw(raw: Record<string, unknown>): AlgorithmDeviceParam {
  return toAlgorithmDeviceParam(raw as unknown as AlgorithmDeviceParamDto)
}

/** 后端宽松对象 → 用例参数 Domain（definition 内嵌列表项） */
export function toAlgorithmCaseParamFromRaw(raw: Record<string, unknown>): AlgorithmCaseParam {
  return toAlgorithmCaseParam(raw as unknown as AlgorithmCaseParamDto)
}

/** 后端宽松对象 → 参数映射 Domain（definition.mappings 内嵌列表项） */
export function toParamMappingFromRaw(raw: Record<string, unknown>): ParamMapping {
  return toParamMapping(raw as unknown as ParamMappingDto)
}

/** 后端宽松对象 → 关联维度 Domain（definition.associated_dimensions 内嵌列表项） */
export function toAlgorithmAssociatedDimensionFromRaw(raw: Record<string, unknown>): AlgorithmAssociatedDimension {
  const rec = raw as Record<string, unknown>
  return {
    id: (rec?.id as number) ?? 0,
    dimensionId: (rec?.dimension_id as number) ?? 0,
    name: (rec?.name as string) ?? '',
    description: rec?.description as string | undefined,
    type: rec?.type as string | undefined,
    weight: (rec?.weight as number) ?? 1,
    isDefault: Boolean(rec?.is_default ?? false),
  }
}

/** AlgorithmCaseParamDto → AlgorithmCaseParam */
export function toAlgorithmCaseParam(dto: AlgorithmCaseParamDto): AlgorithmCaseParam {
  return {
    id: dto?.id ?? 0,
    algorithmType: dto?.algorithm_type ?? '',
    paramCode: dto?.param_code ?? '',
    paramName: dto?.param_name,
    label: dto?.label,
    paramType: dto?.param_type ?? 'text',
    required: dto?.required ?? false,
    defaultValue: dto?.default_value,
    helpText: dto?.help_text,
    uiOrder: dto?.ui_order ?? 0,
    hidden: dto?.hidden ?? false,
    scope: (dto?.scope ?? 'common') as AlgorithmCaseParam['scope'],
    minValue: dto?.min_value,
    maxValue: dto?.max_value,
    step: dto?.step,
    unit: dto?.unit,
    annotationCode: dto?.annotation_code,
    fieldPath: dto?.field_path,
  }
}

/** 参数列表（{ parameters, total }）→ Domain */
export function toAlgorithmParamList(dto: AlgorithmParamListDto | null | undefined): AlgorithmParamList {
  return {
    parameters: (dto?.parameters ?? []).map(toAlgorithmDeviceParamFromRaw),
    total: dto?.total ?? 0,
  }
}

// ===== 映射 =====

/** ParamMappingDto → ParamMapping */
export function toParamMapping(dto: ParamMappingDto): ParamMapping {
  return {
    id: dto?.id ?? 0,
    algorithmType: dto?.algorithm_type ?? '',
    source: dto?.source ?? '',
    sourceParam: dto?.source_param ?? '',
    sourceDirection: dto?.source_direction ?? 'output',
    dimensionId: dto?.dimension_id,
    dimensionName: dto?.dimension_name,
    targetParam: dto?.target_param ?? '',
    transformType: dto?.transform_type ?? 'none',
  }
}

/** 映射列表 */
export function toParamMappingList(dto: ParamMappingListDto | null | undefined): ParamMapping[] {
  return (dto?.mappings ?? []).map(toParamMapping)
}

// ===== 分组 =====

/** AlgorithmGroupDto → AlgorithmGroup */
export function toAlgorithmGroup(dto: AlgorithmGroupDto): AlgorithmGroup {
  return {
    id: dto?.id ?? 0,
    name: dto?.name ?? '',
    description: dto?.description,
    icon: dto?.icon,
    displayOrder: dto?.display_order ?? 0,
    algorithmCount: dto?.algorithm_count ?? 0,
    createdAt: dto?.created_at,
    updatedAt: dto?.updated_at,
  }
}

/** 分组列表 */
export function toAlgorithmGroupList(dto: AlgorithmGroupListDto | null | undefined): AlgorithmGroup[] {
  return (dto?.data ?? []).map(toAlgorithmGroup)
}

// ===== 选项 =====

/** AlgorithmOptionDto → AlgorithmOption */
export function toAlgorithmOption(dto: AlgorithmOptionDto): AlgorithmOption {
  return {
    value: dto?.value ?? '',
    name: dto?.name ?? '',
    groupId: dto?.group_id,
    groupName: dto?.group_name,
    icon: dto?.icon,
  }
}

/** 选项列表 */
export function toAlgorithmOptionList(dtos: AlgorithmOptionDto[] | null | undefined): AlgorithmOption[] {
  return (dtos ?? []).map(toAlgorithmOption)
}

// ===== 算法-维度关联 =====

/** AlgorithmDimensionsDto → AlgorithmDimensions（weights 键为数字字符串，需转 number 键） */
export function toAlgorithmDimensions(dto: AlgorithmDimensionsDto | null | undefined): AlgorithmDimensions {
  const weights: Record<number, number> = {}
  const rawWeights = dto?.weights ?? {}
  for (const key of Object.keys(rawWeights)) {
    weights[Number(key)] = rawWeights[key]
  }
  return {
    dimensions: (dto?.dimensions ?? []).map(dim => ({
      id: dim?.id ?? 0,
      dimensionId: dim?.dimension_id ?? 0,
      name: dim?.name ?? '',
      description: dim?.description,
      type: dim?.type,
      weight: dim?.weight ?? 1,
      isDefault: dim?.is_default ?? false,
    })),
    dimensionIds: dto?.dimension_ids ?? [],
    defaultDimensionId: dto?.default_dimension_id ?? null,
    weights,
  }
}

/** DimensionParamDto → DimensionParam */
export function toDimensionParam(dto: DimensionParamDto): DimensionParam {
  return {
    id: dto?.id ?? 0,
    dimensionId: dto?.dimension_id ?? 0,
    code: dto?.code ?? dto?.param_code ?? '',
    name: dto?.name ?? dto?.param_name,
    label: dto?.label,
    fieldType: dto?.field_type ?? 'text',
    paramDirection: dto?.param_direction,
    fieldPath: dto?.field_path,
    aggRole: dto?.agg_role,
    outputRole: dto?.output_role,
    visibleInReport: dto?.visible_in_report ?? true,
    required: dto?.required ?? false,
    defaultValue: dto?.default_value,
    helpText: dto?.help_text,
    uiOrder: dto?.ui_order ?? 0,
  }
}

/** 维度参数列表（{ params: [...] }） */
export function toDimensionParamList(dto: DimensionParamsResultDto | null | undefined): DimensionParam[] {
  return (dto?.params ?? []).map(toDimensionParam)
}

/** 后端宽松对象 → 表单字段（form-schema 接口输出已为 camelCase，仅做形状收敛） */
export function toFormFieldFromRaw(raw: Record<string, unknown>): FormField {
  const rec = raw as Record<string, unknown>
  return {
    fieldCode: (rec?.fieldCode as string) ?? '',
    fieldName: (rec?.fieldName as string) ?? '',
    fieldType: (rec?.fieldType as string) ?? 'text',
    required: Boolean(rec?.required ?? false),
    defaultValue: rec?.defaultValue,
    component: rec?.component as string | undefined,
    options: rec?.options as FormField['options'],
    validation: rec?.validation as FormField['validation'],
    helpText: rec?.helpText as string | undefined,
    hidden: Boolean(rec?.hidden ?? false),
    uiOrder: (rec?.uiOrder as number) ?? 0,
    uiGroup: (rec?.uiGroup as string) ?? '',
    scope: rec?.scope as string | undefined,
  }
}

/** 后端宽松对象 → 表单字段组 */
export function toFormFieldGroupFromRaw(raw: Record<string, unknown>): FormFieldGroup {
  const rec = raw as Record<string, unknown>
  return {
    name: (rec?.name as string) ?? '',
    label: (rec?.label as string) ?? '',
    fields: ((rec?.fields as Record<string, unknown>[]) ?? []).map(toFormFieldFromRaw),
  }
}

// ===== 表单 Schema =====

/** AlgorithmFormSchemaDto → FormSchema（后端该接口已直接输出 camelCase） */
export function toFormSchema(dto: AlgorithmFormSchemaDto): FormSchema {
  return {
    algorithmType: dto?.algorithmType ?? '',
    algorithmName: dto?.algorithmName ?? '',
    category: dto?.category,
    description: dto?.description,
    groups: (dto?.groups ?? []).map(toFormFieldGroupFromRaw),
    fields: (dto?.fields ?? []).map(toFormFieldFromRaw),
  }
}

// ===== 其他操作结果 =====

/** ReloadConfigDto → ReloadConfigResult */
export function toReloadConfigResult(dto: ReloadConfigDto): ReloadConfigResult {
  return {
    success: dto?.success ?? false,
    message: dto?.message ?? '',
    reloadTime: dto?.reload_time,
  }
}

/** AlgorithmImportResultDto → AlgorithmImportResult */
export function toAlgorithmImportResult(dto: AlgorithmImportResultDto): AlgorithmImportResult {
  return {
    imported: dto?.imported ?? [],
  }
}

/** AlgorithmBulkDeleteResultDto → AlgorithmBulkDeleteResult */
export function toAlgorithmBulkDeleteResult(dto: AlgorithmBulkDeleteResultDto): AlgorithmBulkDeleteResult {
  return {
    deletedTypes: dto?.deleted_types ?? [],
  }
}

/** AlgorithmReferenceParamDto → ReferenceParam */
export function toReferenceParam(dto: AlgorithmReferenceParamDto): ReferenceParam {
  return {
    id: dto?.id,
    code: dto?.code ?? '',
    name: dto?.name ?? '',
    type: dto?.type ?? 'text',
    helpText: dto?.help_text,
    algorithmType: dto?.algorithm_type,
    annotationCode: dto?.annotation_code,
    annotationFormat: dto?.annotation_format,
    fieldPath: dto?.field_path,
    mergeMode: dto?.merge_mode,
  }
}

/** 参考参数列表 */
export function toReferenceParamList(dtos: AlgorithmReferenceParamDto[] | null | undefined): ReferenceParam[] {
  return (dtos ?? []).map(toReferenceParam)
}

/** ReferenceParam（Domain）→ DTO（请求体） */
export function toReferenceParamDto(param: Partial<ReferenceParam> & { code: string }): AlgorithmReferenceParamDto {
  return {
    id: param.id,
    code: param.code,
    name: param.name ?? param.code,
    type: param.type ?? 'text',
    help_text: param.helpText,
    algorithm_type: param.algorithmType,
    annotation_code: param.annotationCode,
    annotation_format: param.annotationFormat,
    field_path: param.fieldPath,
    merge_mode: param.mergeMode,
  }
}

// ===== 提交方向转换：Domain → snake_case 请求体 =====

/** AlgorithmCaseParam（camelCase）→ 算法定义内嵌 case_params 列表项（snake_case）。
 *  保留 id：后端 _update_case_params 以 id 对账既有参数（未提交 id 会被软删除）；
 *  tempId/component 等前端态字段不提交。 */
export function toCaseParamItemDto(param: Partial<AlgorithmCaseParam>): Record<string, any> {
  const result: Record<string, any> = {}
  if (param.id !== undefined) result.id = param.id
  if (param.paramCode !== undefined) result.param_code = param.paramCode
  if (param.paramName !== undefined) result.param_name = param.paramName
  if (param.label !== undefined) result.label = param.label
  if (param.paramType !== undefined) result.param_type = param.paramType
  if (param.required !== undefined) result.required = param.required
  if (param.defaultValue !== undefined) result.default_value = param.defaultValue
  if (param.helpText !== undefined) result.help_text = param.helpText
  if (param.uiOrder !== undefined) result.ui_order = param.uiOrder
  if (param.hidden !== undefined) result.hidden = param.hidden
  if (param.scope !== undefined) result.scope = param.scope
  if (param.minValue !== undefined) result.min_value = param.minValue
  if (param.maxValue !== undefined) result.max_value = param.maxValue
  if (param.step !== undefined) result.step = param.step
  if (param.unit !== undefined) result.unit = param.unit
  if (param.annotationCode !== undefined) result.annotation_code = param.annotationCode
  if (param.fieldPath !== undefined) result.field_path = param.fieldPath
  return result
}

/** AlgorithmDeviceParam（camelCase）→ 算法定义内嵌 device_params/api_params 列表项（snake_case）。
 *  device/api 两列表共用：后端 _update_params 以同一套字段消费。
 *  保留 id：后端以 id 对账既有参数（existing_ids - submitted_ids 软删除），丢 id 会误删既有行；
 *  无 id 且 param_code 为空的新行为不完整行（blur 自动保存同样拒绝保存空码行），提交后
 *  按码 upsert 无从对账、只会写成空码脏行，故跳过。tempId/optionsSource 等非后端字段不提交。 */
export function toDeviceParamItemDto(param: Partial<AlgorithmDeviceParam>): Record<string, any> | null {
  if (!param.id && !param.paramCode) return null
  const result: Record<string, any> = {}
  if (param.id !== undefined) result.id = param.id
  if (param.paramCode !== undefined) result.param_code = param.paramCode
  if (param.paramName !== undefined) result.param_name = param.paramName
  if (param.label !== undefined) result.label = param.label
  if (param.paramType !== undefined) result.param_type = param.paramType
  if (param.direction !== undefined) result.direction = param.direction
  if (param.required !== undefined) result.required = param.required
  if (param.defaultValue !== undefined) result.default_value = param.defaultValue
  if (param.helpText !== undefined) result.help_text = param.helpText
  if (param.uiOrder !== undefined) result.ui_order = param.uiOrder
  if (param.hidden !== undefined) result.hidden = param.hidden
  return result
}

/** ParamMapping（camelCase）→ 算法定义内嵌 mappings 列表项（snake_case）。
 *  保留 id：后端 _update_mappings 以 id 对账既有映射（未提交 id 会被软删除）；
 *  dimensionName/paramName 为前端展示字段不提交。
 *  无 id 且 sourceParam/targetParam 未填齐的新行为不完整行（blur 自动保存同样拒绝），
 *  提交会被后端原样建为空键值脏行，故跳过。 */
export function toParamMappingItemDto(mapping: Partial<ParamMapping>): Record<string, any> | null {
  if (!mapping.id && (!mapping.sourceParam || !mapping.targetParam)) return null
  const result: Record<string, any> = {}
  if (mapping.id !== undefined) result.id = mapping.id
  if (mapping.source !== undefined) result.source = mapping.source
  if (mapping.sourceParam !== undefined) result.source_param = mapping.sourceParam
  if (mapping.sourceDirection !== undefined) result.source_direction = mapping.sourceDirection
  if (mapping.dimensionId !== undefined) result.dimension_id = mapping.dimensionId
  if (mapping.targetParam !== undefined) result.target_param = mapping.targetParam
  if (mapping.transformType !== undefined) result.transform_type = mapping.transformType
  return result
}

/** Record<source_type, ParamMapping[]> → snake_case mappings 请求体（组键原样透传，逐项深度转换） */
function toMappingsDto(mappings: Record<string, ParamMapping[]>): Record<string, any> {
  const result: Record<string, any> = {}
  for (const [sourceType, list] of Object.entries(mappings ?? {})) {
    result[sourceType] = (list ?? [])
      .map(toParamMappingItemDto)
      .filter((item): item is Record<string, any> => item !== null)
  }
  return result
}

/** AlgorithmAssociatedDimension（camelCase）→ 算法定义内嵌 associated_dimensions 列表项（snake_case）。
 *  对账键是 dimension_id：后端 _update_associated_dimensions 以 dimension_id 对账既有关联
 *  （未提交的 dimension_id 会被软删除）。其 ``or dim_data.get('id')`` 回退仅供历史调用方兼容，
 *  本适配恒传 dimension_id、绝不透传关系行 id（Domain 的 id 是关联行主键，不是维度 id，
 *  透传会被回退分支误当维度 id 对账——错位更新或建脏关联）。
 *  name/type/description 为展示字段不提交；未选维度的新行 dimension_id 为空，后端按空跳过。 */
export function toAssociatedDimensionItemDto(dim: Partial<AlgorithmAssociatedDimension>): Record<string, any> {
  const result: Record<string, any> = {}
  if (dim.dimensionId !== undefined) result.dimension_id = dim.dimensionId
  if (dim.weight !== undefined) result.weight = dim.weight
  if (dim.isDefault !== undefined) result.is_default = dim.isDefault
  return result
}

/** AlgorithmDefinition（camelCase）→ snake_case 请求体 DTO */
export function toAlgorithmDefinitionDto(data: Partial<AlgorithmDefinition>): Record<string, any> {
  const result: Record<string, any> = {}
  if (data.type !== undefined) result.type = data.type
  if (data.name !== undefined) result.name = data.name
  if (data.groupId !== undefined) result.group_id = data.groupId
  if (data.groupName !== undefined) result.group_name = data.groupName
  if (data.category !== undefined) result.category = data.category
  if (data.description !== undefined) result.description = data.description
  if (data.status !== undefined) result.status = data.status
  if (data.icon !== undefined) result.icon = data.icon
  if (data.displayOrder !== undefined) result.display_order = data.displayOrder
  if (data.deviceParams !== undefined) {
    result.device_params = data.deviceParams
      .map(toDeviceParamItemDto)
      .filter((item): item is Record<string, any> => item !== null)
  }
  if (data.apiParams !== undefined) {
    result.api_params = data.apiParams
      .map(toDeviceParamItemDto)
      .filter((item): item is Record<string, any> => item !== null)
  }
  if (data.caseParams !== undefined) result.case_params = data.caseParams.map(toCaseParamItemDto)
  if (data.params !== undefined) result.params = data.params
  if (data.mappings !== undefined) result.mappings = toMappingsDto(data.mappings)
  if (data.associatedDimensions !== undefined) {
    result.associated_dimensions = data.associatedDimensions.map(toAssociatedDimensionItemDto)
  }
  if (data.dimensionRelations !== undefined) result.dimension_relations = data.dimensionRelations
  if (data.referenceParams !== undefined) result.reference_params = data.referenceParams
  return result
}

/** ParamMapping（camelCase）→ snake_case 请求体 */
export function toParamMappingDto(data: Partial<ParamMapping>): Record<string, any> {
  const result: Record<string, any> = {}
  if (data.algorithmType !== undefined) result.algorithm_type = data.algorithmType
  if (data.source !== undefined) result.source = data.source
  if (data.sourceParam !== undefined) result.source_param = data.sourceParam
  if (data.sourceDirection !== undefined) result.source_direction = data.sourceDirection
  if (data.dimensionId !== undefined) result.dimension_id = data.dimensionId
  if (data.dimensionName !== undefined) result.dimension_name = data.dimensionName
  if (data.targetParam !== undefined) result.target_param = data.targetParam
  if (data.transformType !== undefined) result.transform_type = data.transformType
  return result
}

// ===== 用例专属参数 =====

/** 用例专属参数请求体（Domain → snake_case DTO） */
export interface CaseParamUpsertDto {
  algorithm_type?: string
  param_code?: string
  param_name?: string
  label?: string
  param_type?: string
  required?: boolean
  default_value?: unknown
  help_text?: string
  ui_order?: number
  hidden?: boolean
  scope?: string
  min_value?: number
  max_value?: number
  step?: number
  unit?: string
  annotation_code?: string | null
  field_path?: string | null
}

/** AlgorithmCaseParam（Domain）→ 请求体 DTO */
export function toCaseParamUpsertDto(param: Partial<AlgorithmCaseParam>): CaseParamUpsertDto {
  return {
    algorithm_type: param.algorithmType,
    param_code: param.paramCode,
    param_name: param.paramName,
    label: param.label,
    param_type: param.paramType,
    required: param.required,
    default_value: param.defaultValue,
    help_text: param.helpText,
    ui_order: param.uiOrder,
    hidden: param.hidden,
    scope: param.scope,
    min_value: param.minValue,
    max_value: param.maxValue,
    step: param.step,
    unit: param.unit,
    annotation_code: param.annotationCode,
    field_path: param.fieldPath,
  }
}

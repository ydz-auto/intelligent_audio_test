/**
 * 算法配置 DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换层）。
 * 对照 api_gateway/routes/algorithm_bp.py + task_service/application/algorithm/
 * algorithm_crud_service.py 序列化输出（INT-297 统一分页信封 {items,total,page,per_page,pages}）。
 * 读侧：snake_case 响应 → camelCase Domain；写侧：camelCase 表单载荷 → snake_case 请求体。
 */
import {
  CASE_PARAM_SCOPES,
  type AlgorithmDefinition,
  type AlgorithmGroup,
  type AlgorithmMappings,
  type CaseParam,
  type CaseParamScope,
  type DeviceApiParam,
  type DimensionParam,
  type DimensionRelation,
  type ParamMapping,
  type ReferenceParam,
} from '@/domain/models/algorithmConfig'

/**
 * 用例参数 scope 归一：后端词表 = common / physical / http_api / websocket_api
 * （旧 common/api/e2e 已废弃）。未知值回落 common，避免把脏值写回。
 */
function toCaseParamScope(value: unknown): CaseParamScope {
  const scope = typeof value === 'string' ? value : ''
  return (CASE_PARAM_SCOPES as readonly string[]).includes(scope)
    ? (scope as CaseParamScope)
    : 'common'
}

/* ───────────────────────── 响应 DTO（snake_case） ───────────────────────── */

/** 算法定义详情/列表项（对应 AlgorithmDetailResponse 序列化） */
export interface AlgorithmDefinitionDto {
  id: number
  type: string
  name: string
  group_id?: number | null
  group_name?: string | null
  category?: string | null
  description?: string | null
  status?: string
  icon?: string | null
  display_order?: number
  device_params?: Array<Record<string, unknown>>
  case_params?: Array<Record<string, unknown>>
  /** 兼容字段：device_params 别名（部分服务同时输出 params） */
  params?: Array<Record<string, unknown>>
  reference_params?: Array<Record<string, unknown>>
  /** 按 source 分组：device / evaluation（evaluation 项带 dimension_id） */
  mappings?: Record<string, Array<Record<string, unknown>>>
  associated_dimensions?: Array<Record<string, unknown>>
  dimension_relations?: Array<Record<string, unknown>>
  has_draft?: boolean
  /** 引用该算法的用例数（INT-591 §154 case_count；后端未返回时 infra api 层按用例引用聚合兜底） */
  case_count?: number | null
  revision?: number
  created_at?: string
  updated_at?: string
}

/** 算法定义列表（INT-297 统一分页信封） */
export interface AlgorithmDefinitionListDto {
  items: AlgorithmDefinitionDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** 算法分组（对应 AlgorithmGroupItem 序列化） */
export interface AlgorithmGroupDto {
  id: number
  name: string
  description?: string | null
  icon?: string | null
  display_order?: number
  algorithm_count?: number
  created_at?: string
  updated_at?: string
}

/** 分组列表（INT-297 统一分页信封） */
export interface AlgorithmGroupListDto {
  items: AlgorithmGroupDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** POST /algorithm/reload（ReloadConfigResponse） */
export interface ReloadConfigDto {
  success?: boolean
  message?: string
  reload_time?: string
}

/** POST /algorithm/bulk-delete（AlgorithmDeleteResponse 子集） */
export interface AlgorithmBulkDeleteResultDto {
  deleted_types?: string[]
  message?: string
}

/** POST /algorithm/import */
export interface AlgorithmImportResultDto {
  imported?: string[]
}

/** PUT /algorithm/definitions/draft（草稿保存响应 data；后端仅回 saved + 服务端 saved_at，INT-683） */
export interface AlgorithmDraftSaveResultDto {
  saved?: boolean
  algorithm_type?: string
  /** 服务端最后保存时间（ISO，footer「上次保存 HH:mm:ss」消费；缺省时前端取本端 now） */
  saved_at?: string
}

/** GET /evaluation/dimensions/options（维度选项下拉；evaluation 域 DTO，算法/评估页共用） */
export interface DimensionOptionsResultDto {
  dimensions?: Array<{
    id: number
    name: string
    description?: string | null
    /** main / sub */
    dimension_type?: string
    category_id?: number | null
    task_type_code?: string | null
    requires_audio?: boolean
  }>
}

/** GET /algorithm/dimension-params/{dimension_id}（评估维度参数列表项） */
export interface DimensionParamDto {
  id?: number | null
  dimension_id?: number | null
  dimension_name?: string | null
  code?: string | null
  name?: string | null
  label?: string | null
  field_type?: string | null
  required?: boolean | null
  default_value?: unknown
  help_text?: string | null
  ui_order?: number | null
  pass_threshold?: number | null
}

/* ───────────────────────── 读侧：snake_case → camelCase Domain ───────────────────────── */

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null
    ? (value as Record<string, unknown>)
    : {}
}

function str(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function nullableStr(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null
}

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function bool(value: unknown): boolean {
  return Boolean(value)
}

/** 设备/API 参数列表项 → Domain DeviceApiParam */
export function toDeviceApiParam(raw: unknown): DeviceApiParam {
  const r = asRecord(raw)
  return {
    id: num(r.id) ?? 0,
    deviceId: num(r.device_id),
    paramCode: str(r.param_code),
    paramName: nullableStr(r.param_name),
    label: nullableStr(r.label),
    paramType: str(r.param_type) || 'text',
    direction: r.direction === 'output' ? 'output' : 'input',
    required: bool(r.required),
    defaultValue: nullableStr(r.default_value),
    helpText: nullableStr(r.help_text),
    uiOrder: num(r.ui_order) ?? 0,
    hidden: bool(r.hidden),
  }
}

/** 用例专属参数列表项 → Domain CaseParam */
export function toCaseParam(raw: unknown): CaseParam {
  const r = asRecord(raw)
  return {
    id: num(r.id) ?? 0,
    paramCode: str(r.param_code),
    paramName: nullableStr(r.param_name),
    label: nullableStr(r.label),
    paramType: str(r.param_type) || 'text',
    required: bool(r.required),
    defaultValue: nullableStr(r.default_value),
    helpText: nullableStr(r.help_text),
    uiOrder: num(r.ui_order) ?? 0,
    hidden: bool(r.hidden),
    scope: toCaseParamScope(r.scope),
    minValue: num(r.min_value),
    maxValue: num(r.max_value),
    step: num(r.step),
    unit: nullableStr(r.unit),
    annotationCode: nullableStr(r.annotation_code),
    fieldPath: nullableStr(r.field_path),
  }
}

/** 参考参数列表项 → Domain ReferenceParam */
export function toReferenceParam(raw: unknown): ReferenceParam {
  const r = asRecord(raw)
  const merge = r.merge_mode
  const mergeMode =
    merge === 'concat' || merge === 'collect' || merge === 'first'
      ? merge === 'concat' ? 'join' : merge
      : null
  return {
    id: num(r.id) ?? 0,
    code: str(r.code),
    name: str(r.name),
    type: str(r.type) || 'text',
    annotationCode: nullableStr(r.annotation_code),
    annotationFormat: nullableStr(r.annotation_format),
    fieldPath: nullableStr(r.field_path),
    mergeMode,
    helpText: nullableStr(r.help_text),
  }
}

/**
 * 参数映射列表项 → Domain ParamMapping。
 * 读侧把后端全字段映射进 camelCase Domain（INT-1160 返工）：id / source / source_direction /
 * source_param / param_name / dimension_id / dimension_name / target_param / transform_type；
 * param_name / target_param_name 后端 _serialize_mappings 不下发，由前端按 code 查参数表兜底。
 * evaluation 行 target_param 兼容存量维度名形态与维度内目标参数两种取值。
 */
export function toParamMapping(raw: unknown): ParamMapping {
  const r = asRecord(raw)
  const transform = r.transform_type
  const transformType =
    transform === 'uppercase' ||
    transform === 'lowercase' ||
    transform === 'json_parse' ||
    transform === 'rttm_to_obj' ||
    transform === 'stm_to_obj' ||
    transform === 'base64'
      ? transform
      : 'none'
  const source = r.source
  const parsedSource: ParamMapping['source'] =
    source === 'case' ||
    source === 'case_config' ||
    source === 'reference' ||
    source === 'device' ||
    source === 'api'
      ? source
      : typeof source === 'string' && source.length > 0
        ? source
        : null
  return {
    id: num(r.id) ?? 0,
    source: parsedSource,
    sourceDirection: nullableStr(r.source_direction),
    sourceParam: str(r.source_param),
    paramName: nullableStr(r.param_name),
    dimensionId: num(r.dimension_id),
    dimensionName: nullableStr(r.dimension_name),
    targetParam: str(r.target_param),
    targetParamName: nullableStr(r.target_param_name),
    transformType,
  }
}

/** 关联维度列表项 → Domain DimensionRelation（名称后端不返回，由前端 dimensionOptions 补） */
export function toDimensionRelation(raw: unknown): DimensionRelation {
  const r = asRecord(raw)
  return {
    id: num(r.id) ?? 0,
    dimensionId: num(r.dimension_id) ?? 0,
    dimensionName: nullableStr(r.dimension_name) ?? '',
    weight: typeof r.weight === 'number' ? r.weight : 1,
    isDefault: bool(r.is_default),
  }
}

/** 评估维度参数列表项 → Domain DimensionParam（evaluation 映射目标参数选项） */
export function toDimensionParam(raw: unknown): DimensionParam {
  const r = asRecord(raw)
  return {
    id: num(r.id) ?? 0,
    dimensionId: num(r.dimension_id) ?? 0,
    dimensionName: nullableStr(r.dimension_name),
    // 实测维度参数响应同时下发 code/param_code（name/param_name），双键兜底
    code: str(r.code) || str(r.param_code),
    name: nullableStr(r.name) || nullableStr(r.param_name),
    label: nullableStr(r.label),
    fieldType: nullableStr(r.field_type),
    required: bool(r.required),
    defaultValue: r.default_value,
    helpText: nullableStr(r.help_text),
    uiOrder: num(r.ui_order),
    passThreshold: num(r.pass_threshold),
  }
}

/** 映射按 source 分组（device / evaluation；算法级 api 已迁移到 API 实例作用域） */
function toMappings(
  raw?: Record<string, Array<Record<string, unknown>>>
): AlgorithmMappings {
  const source = asRecord(raw)
  const list = (key: string): ParamMapping[] =>
    Array.isArray(source[key]) ? source[key].map(toParamMapping) : []
  return {
    device: list('device'),
    evaluation: list('evaluation'),
  }
}

/** AlgorithmDefinitionDto → Domain AlgorithmDefinition */
export function toAlgorithmDefinition(dto: AlgorithmDefinitionDto): AlgorithmDefinition {
  const deviceParams = Array.isArray(dto.device_params)
    ? dto.device_params
    : Array.isArray(dto.params)
      ? dto.params
      : []
  const caseParams = Array.isArray(dto.case_params) ? dto.case_params : []
  const referenceParams = Array.isArray(dto.reference_params)
    ? dto.reference_params
    : []
  const associatedRaw = Array.isArray(dto.associated_dimensions)
    ? dto.associated_dimensions
    : Array.isArray(dto.dimension_relations)
      ? dto.dimension_relations
      : []
  return {
    id: num(dto.id) ?? 0,
    type: str(dto.type),
    name: str(dto.name),
    groupId: num(dto.group_id),
    groupName: nullableStr(dto.group_name),
    category: nullableStr(dto.category),
    description: nullableStr(dto.description),
    status: dto.status === 'offline' ? 'offline' : 'online',
    icon: nullableStr(dto.icon),
    displayOrder: num(dto.display_order) ?? 0,
    deviceParams: deviceParams.map(toDeviceApiParam),
    caseParams: caseParams.map(toCaseParam),
    referenceParams: referenceParams.map(toReferenceParam),
    mappings: toMappings(dto.mappings as Record<string, Array<Record<string, unknown>>>),
    associatedDimensions: associatedRaw.map(toDimensionRelation),
    // §3.4/§154/P3-1（INT-1319）：后端返回 case_count 时直接消费；未返回（null）时
    // 由 useAlgorithmCaseCounts 异步补齐（列表首屏不等逐算法用例聚合）
    caseCount: num(dto.case_count),
    hasDraft: dto.has_draft,
    revision: dto.revision,
    createdAt: str(dto.created_at),
    updatedAt: str(dto.updated_at),
  }
}

/** 算法定义列表（INT-297 信封）→ Domain[] */
export function toAlgorithmDefinitionList(
  dto: AlgorithmDefinitionListDto
): AlgorithmDefinition[] {
  return (dto?.items ?? []).map(toAlgorithmDefinition)
}

/** AlgorithmGroupDto → Domain AlgorithmGroup */
export function toAlgorithmGroup(dto: AlgorithmGroupDto): AlgorithmGroup {
  return {
    id: num(dto.id) ?? 0,
    name: str(dto.name),
    description: nullableStr(dto.description),
    icon: nullableStr(dto.icon),
    displayOrder: num(dto.display_order) ?? 0,
    algorithmCount: num(dto.algorithm_count) ?? 0,
    createdAt: str(dto.created_at),
    updatedAt: str(dto.updated_at),
  }
}

/** 分组列表（INT-297 信封）→ Domain[] */
export function toAlgorithmGroupList(
  dto: AlgorithmGroupListDto
): AlgorithmGroup[] {
  return (dto?.items ?? []).map(toAlgorithmGroup)
}

/** POST /algorithm/reload → { success, reloadTime } */
export function toReloadConfigResult(
  dto: ReloadConfigDto
): { success: boolean; reloadTime: string } {
  return {
    success: dto?.success ?? false,
    reloadTime: str(dto?.reload_time),
  }
}

/** POST /algorithm/bulk-delete → 成功/失败计数（deleted_types 与请求 types 对账） */
export function toBulkDeleteResult(
  dto: AlgorithmBulkDeleteResultDto,
  requestedTypes: string[]
): { successCount: number; failedCount: number } {
  const deleted = new Set(dto?.deleted_types ?? [])
  const successCount = requestedTypes.filter((t) => deleted.has(t)).length
  return { successCount, failedCount: requestedTypes.length - successCount }
}

/** POST /algorithm/import → { importedCount } */
export function toImportResult(
  dto: AlgorithmImportResultDto
): { importedCount: number } {
  return { importedCount: (dto?.imported ?? []).length }
}

/* ───────────────────────── 写侧：camelCase 表单载荷 → snake_case 请求体 ───────────────────────── */

type Row = Record<string, unknown>

/** 设备参数行（DeviceApiParamRow camelCase）→ device_params 列表项 */
function toDeviceApiParamItemDto(row: Row): Row {
  const r = row
  return {
    param_code: str(r.paramCode),
    param_name: nullableStr(r.paramName),
    label: nullableStr(r.paramName),
    param_type: str(r.paramType) || 'text',
    direction: r.direction === 'output' ? 'output' : 'input',
    required: bool(r.required),
    default_value: nullableStr(r.defaultValue),
    help_text: nullableStr(r.helpText),
    ui_order: typeof r.uiOrder === 'number' ? r.uiOrder : 0,
    hidden: bool(r.hidden),
  }
}

/** 用例参数行（CaseParamRow camelCase）→ case_params 列表项 */
function toCaseParamItemDto(row: Row): Row {
  const r = row
  return {
    param_code: str(r.paramCode),
    param_name: nullableStr(r.paramName),
    label: nullableStr(r.paramName),
    param_type: str(r.paramType) || 'text',
    required: bool(r.required),
    default_value: nullableStr(r.defaultValue),
    help_text: nullableStr(r.helpText),
    ui_order: typeof r.uiOrder === 'number' ? r.uiOrder : 0,
    hidden: bool(r.hidden),
    scope: toCaseParamScope(r.scope),
    min_value: r.minValue !== '' && r.minValue != null ? Number(r.minValue) : null,
    max_value: r.maxValue !== '' && r.maxValue != null ? Number(r.maxValue) : null,
    step: r.step !== '' && r.step != null ? Number(r.step) : null,
    unit: nullableStr(r.unit),
    annotation_code: nullableStr(r.annotationCode),
    field_path: nullableStr(r.fieldPath),
  }
}

/** 参考参数行（ReferenceParamRow camelCase）→ reference_params 列表项 */
function toReferenceParamItemDto(row: Row): Row {
  const r = row
  return {
    code: str(r.code),
    name: str(r.name),
    type: str(r.type) || 'text',
    annotation_code: nullableStr(r.annotationCode),
    annotation_format: nullableStr(r.annotationFormat),
    field_path: nullableStr(r.fieldPath),
    merge_mode:
      r.mergeMode === 'join' || r.mergeMode === 'collect' || r.mergeMode === 'first'
        ? r.mergeMode === 'join' ? 'concat' : r.mergeMode
        : null,
    help_text: nullableStr(r.helpText),
  }
}

/** 参数映射行（MappingRow camelCase）→ mappings 列表项；
 *  写侧把 source / source_direction / dimension_id 原样提交（INT-1160 返工）：
 *  evaluation 行 dimension_id 从 row.dimensionId（数字）优先、维度名对账兜底；
 *  target_param 兼容维度内目标参数代码与存量维度名两种形态。
 *  设备节 source = 节类型（device，后端按节派生）；评估节 source = 行来源（缺省 case）。 */
function toMappingItemDto(
  row: Row,
  section: 'device' | 'evaluation',
  dimensionIdByName?: Map<string, number>
): Row {
  const r = row
  const transform = r.transformType
  const transformType =
    transform === 'uppercase' ||
    transform === 'lowercase' ||
    transform === 'json_parse' ||
    transform === 'rttm_to_obj' ||
    transform === 'stm_to_obj' ||
    transform === 'base64'
      ? transform
      : 'none'
  const source =
    section === 'evaluation'
      ? r.source === 'case' ||
        r.source === 'case_config' ||
        r.source === 'reference' ||
        r.source === 'device'
        ? r.source
        : r.source !== undefined && r.source !== ''
          ? r.source
          : 'case'
      : section
  const dimensionId =
    r.dimensionId !== undefined && r.dimensionId !== '' && r.dimensionId != null
      ? Number(r.dimensionId)
      : dimensionIdByName?.get(str(r.dimensionName) || str(r.targetParam))
  const item: Row = {
    source,
    source_param: str(r.sourceParam),
    source_direction: str(r.sourceDirection) || 'output',
    target_param: str(r.targetParam),
    transform_type: transformType,
  }
  if (dimensionId != null && Number.isFinite(dimensionId)) item.dimension_id = dimensionId
  return item
}

/** 关联维度行（DimensionRow camelCase）→ associated_dimensions 列表项（dimension_id 对账键） */
function toDimensionRelationItemDto(row: Row): Row {
  const r = row
  const weight = r.weight !== '' && r.weight != null ? Number(r.weight) : 1
  return {
    dimension_id: r.dimensionId !== '' && r.dimensionId != null ? Number(r.dimensionId) : null,
    weight: Number.isFinite(weight) ? weight : 1,
    is_default: bool(r.isDefault),
  }
}

/** 保存载荷 → snake_case create/update 请求体（AlgorithmDefinitionCreate/Update 契约） */
export function toAlgorithmDefinitionDto(
  input: {
    type: string
    name: string
    groupId: number | null
    displayOrder: number
    status: 'online' | 'offline'
    description: string
    deviceParams: Row[]
    caseParams: Row[]
    referenceParams: Row[]
    mappings: { device: Row[]; evaluation: Row[] }
    associatedDimensions: Row[]
  },
  dimensionIdByName?: Map<string, number>
): Record<string, unknown> {
  return {
    type: str(input.type),
    name: str(input.name),
    group_id: input.groupId != null ? input.groupId : null,
    display_order: input.displayOrder,
    status: input.status,
    description: nullableStr(input.description),
    device_params: (input.deviceParams ?? []).map(toDeviceApiParamItemDto),
    case_params: (input.caseParams ?? []).map(toCaseParamItemDto),
    reference_params: (input.referenceParams ?? []).map(toReferenceParamItemDto),
    mappings: {
      device: (input.mappings?.device ?? []).map((row) => toMappingItemDto(row, 'device')),
      evaluation: (input.mappings?.evaluation ?? []).map((row) =>
        toMappingItemDto(row, 'evaluation', dimensionIdByName)
      ),
    },
    associated_dimensions: (input.associatedDimensions ?? []).map(
      toDimensionRelationItemDto
    ),
  }
}

/** 分组保存载荷 → snake_case group create/update 请求体 */
export function toAlgorithmGroupDto(input: {
  name: string
  description: string
  icon: string
  displayOrder: number
}): Record<string, unknown> {
  return {
    name: str(input.name),
    description: nullableStr(input.description),
    icon: nullableStr(input.icon),
    display_order: input.displayOrder,
  }
}

/** 批量删除请求体（BulkDeleteRequest） */
export function toBulkDeleteDto(algorithmTypes: string[]): Record<string, unknown> {
  return { algorithm_types: algorithmTypes }
}

/** 导入请求体（AlgorithmImportRequest） */
export function toImportDto(algorithms: unknown[]): Record<string, unknown> {
  return { algorithms }
}

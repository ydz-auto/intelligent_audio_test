/**
 * 参数策略 DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换点）。
 *
 * 读接口：
 * - `GET /algorithm/param-profiles?algorithm_type=X&scope=api`
 *   → 网关 `AlgorithmProfileService.list_profiles` → gRPC `ListParamProfiles`
 *   → data = `{ profiles, total }`；
 * - `GET /algorithm/param-profiles/{id}` → data = 策略详情（含 params / mappings）。
 *
 * 写接口：
 * - `POST /algorithm/param-profiles`、`PUT /algorithm/param-profiles/{id}`
 *   body = ParamProfileSaveRequest（scope / algorithm_type / name / description /
 *   status / params / mappings）；
 * - `POST /algorithm/param-profiles/{id}/clone` body = `{ name, description }`；
 * - `PUT /algorithm/api-scope/{api_id}/binding` body = `{ profile_id }`（null = 解绑）；
 * - `PUT /algorithm/api-scope/{api_id}/overrides` body =
 *   `{ algorithm_type, api_params, mappings }`。
 *
 * 参数行字段（_param_profile_repositories._sync_params 读取口径）：
 * param_code / param_name / label / param_type / direction / required /
 * default_value / validation_rules / help_text / ui_order / hidden / field_path。
 * 映射行字段：source / source_param / source_direction / dimension_id /
 * target_param / transform_type。
 */
import {
  isParamDirection,
  isParamProfileScope,
  isParamProfileStatus,
  isParamTransformType,
  isParamType,
  type ApiScopeOverridesInput,
  type ParamProfile,
  type ParamProfileBinding,
  type ParamProfileCloneInput,
  type ParamProfileInput,
  type ParamProfileMapping,
  type ParamProfileMappingDraft,
  type ParamProfileParam,
  type ParamProfileParamDraft,
} from '@/domain/models/paramProfile'
import type { ParamProfileScope, ParamProfileStatus } from '@/domain/models/paramProfile'

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null
    ? (value as Record<string, unknown>)
    : {}
}

function nullableStr(value: unknown): string | null {
  if (typeof value === 'string') return value === '' ? null : value
  return null
}

/** 文本 / JSON 列统一收敛为字符串（后端 `_text_or_json` 可能存对象） */
function textOrNull(value: unknown): string | null {
  if (typeof value === 'string') return value === '' ? null : value
  if (value == null) return null
  try {
    return JSON.stringify(value)
  } catch {
    return null
  }
}

function num(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))) {
    return Number(value)
  }
  return fallback
}

function nullableNum(value: unknown): number | null {
  if (value == null || value === '') return null
  const parsed = num(value, Number.NaN)
  return Number.isFinite(parsed) ? parsed : null
}

function bool(value: unknown): boolean {
  return value === true || value === 1 || value === '1' || value === 'true'
}

/* ------------------------------------------------------------------ */
/* 读侧                                                                 */
/* ------------------------------------------------------------------ */

export interface ParamProfileListDto {
  profiles?: unknown[]
  total?: number
  bindings?: unknown[]
}

export interface ParamProfileBindingDto {
  api_id: number
  profile_id: number
}

export function toParamProfileParam(raw: unknown): ParamProfileParam {
  const r = asRecord(raw)
  return {
    id: num(r.id),
    paramCode: nullableStr(r.param_code) ?? nullableStr(r.code) ?? '',
    paramName: nullableStr(r.param_name) ?? nullableStr(r.name),
    label: nullableStr(r.label),
    paramType: isParamType(r.param_type) ? r.param_type : isParamType(r.type) ? r.type : 'text',
    direction: isParamDirection(r.direction) ? r.direction : 'input',
    required: bool(r.required),
    defaultValue: textOrNull(r.default_value),
    helpText: nullableStr(r.help_text),
    uiOrder: num(r.ui_order),
    hidden: bool(r.hidden),
    fieldPath: nullableStr(r.field_path),
  }
}

export function toParamProfileMapping(raw: unknown): ParamProfileMapping {
  const r = asRecord(raw)
  return {
    id: num(r.id),
    // 策略映射只服务 API 作用域；后端脏值一律收敛为 api
    source: 'api',
    sourceDirection: isParamDirection(r.source_direction) ? r.source_direction : 'output',
    sourceParam: nullableStr(r.source_param) ?? nullableStr(r.source_field) ?? '',
    dimensionId: nullableNum(r.dimension_id),
    dimensionName: nullableStr(r.dimension_name),
    targetParam: nullableStr(r.target_param) ?? nullableStr(r.target_field) ?? '',
    transformType: isParamTransformType(r.transform_type) ? r.transform_type : 'none',
  }
}

export function toParamProfile(raw: unknown): ParamProfile {
  const r = asRecord(raw)
  return {
    id: num(r.id),
    scope: isParamProfileScope(r.scope) ? r.scope : 'api',
    algorithmType: nullableStr(r.algorithm_type) ?? '',
    name: nullableStr(r.name) ?? '',
    description: nullableStr(r.description),
    status: isParamProfileStatus(r.status) ? r.status : 'online',
    clonedFrom: nullableNum(r.cloned_from),
    config: toApiConfigSnapshot(r.config),
    params: Array.isArray(r.params) ? r.params.map(toParamProfileParam) : [],
    mappings: Array.isArray(r.mappings) ? r.mappings.map(toParamProfileMapping) : [],
    createdAt: nullableStr(r.created_at),
    updatedAt: nullableStr(r.updated_at),
  }
}

/**
 * `config` 快照是不透明 JSON（前端写、前端读）：字段保持 camelCase，
 * 仅做类型收敛，避免与后端 snake_case DTO 混淆。
 */
export function toApiConfigSnapshot(raw: unknown): ApiConfigSnapshot | null {
  if (typeof raw !== 'object' || raw === null) return null
  const r = asRecord(raw)
  const protocol = nullableStr(r.protocol)
  const vendorAdapter = nullableStr(r.vendorAdapter)
  const streaming = typeof r.streaming === 'boolean' ? r.streaming : null
  const audioConfig =
    typeof r.audioConfig === 'object' && r.audioConfig !== null
      ? (r.audioConfig as Record<string, unknown>)
      : null
  const meta =
    typeof r.meta === 'object' && r.meta !== null ? (r.meta as Record<string, unknown>) : null
  if (!protocol && streaming == null && !vendorAdapter && !audioConfig && !meta) return null
  return { protocol, streaming, vendorAdapter, audioConfig, meta }
}

/** GET /algorithm/param-profiles 的 data（`{ profiles, total }` 或裸数组都兼容） */
export function toParamProfileList(payload: unknown): ParamProfile[] {
  if (Array.isArray(payload)) return payload.map(toParamProfile)
  const dto = asRecord(payload) as ParamProfileListDto
  return (dto.profiles ?? []).map(toParamProfile)
}

/** 同一响应的 `bindings`（api_id → profile_id）；缺省 / 非法 = 空数组 */
export function toParamProfileBindingList(payload: unknown): ParamProfileBinding[] {
  const dto = asRecord(payload) as ParamProfileListDto
  if (!Array.isArray(dto.bindings)) return []
  return dto.bindings.map((raw) => {
    const r = asRecord(raw) as Partial<ParamProfileBindingDto>
    return { apiId: num(r.api_id), profileId: num(r.profile_id) }
  })
}

/* ------------------------------------------------------------------ */
/* 写侧                                                                 */
/* ------------------------------------------------------------------ */

export interface ParamProfileParamWriteDto {
  param_code: string
  param_name: string | null
  param_type: string
  direction: string
  required: boolean
  default_value: string | null
  help_text: string | null
  ui_order: number
  hidden: boolean
  field_path: string | null
}

export interface ParamProfileMappingWriteDto {
  source: string
  source_direction: string
  source_param: string
  target_param: string
  dimension_id: number | null
  transform_type: string
}

export interface ParamProfileWriteDto {
  scope: string
  algorithm_type: string
  name: string
  description: string | null
  status: string
  config?: Record<string, unknown> | null
  params: ParamProfileParamWriteDto[]
  mappings: ParamProfileMappingWriteDto[]
}

export interface ParamProfileCloneWriteDto {
  name: string
  description: string | null
}

export interface ApiScopeOverridesWriteDto {
  algorithm_type: string
  api_params: ParamProfileParamWriteDto[]
  mappings: ParamProfileMappingWriteDto[]
}

export function toParamProfileParamDto(draft: ParamProfileParamDraft): ParamProfileParamWriteDto {
  return {
    param_code: draft.paramCode,
    param_name: draft.paramName,
    param_type: draft.paramType,
    direction: draft.direction,
    required: draft.required,
    default_value: draft.defaultValue,
    help_text: draft.helpText,
    ui_order: draft.uiOrder,
    hidden: draft.hidden,
    field_path: draft.fieldPath,
  }
}

export function toParamProfileMappingDto(
  draft: ParamProfileMappingDraft
): ParamProfileMappingWriteDto {
  return {
    source: draft.source,
    source_direction: draft.sourceDirection,
    source_param: draft.sourceParam,
    target_param: draft.targetParam,
    dimension_id: draft.dimensionId,
    transform_type: draft.transformType,
  }
}

export function toParamProfileDto(input: ParamProfileInput): ParamProfileWriteDto {
  return {
    scope: input.scope,
    algorithm_type: input.algorithmType,
    name: input.name,
    description: input.description,
    status: input.status,
    // 快照保持 camelCase 原样透传（读侧 toApiConfigSnapshot 同口径）
    config: input.config
      ? {
          protocol: input.config.protocol,
          streaming: input.config.streaming,
          vendorAdapter: input.config.vendorAdapter,
          audioConfig: input.config.audioConfig,
          meta: input.config.meta,
        }
      : null,
    params: input.params.map(toParamProfileParamDto),
    mappings: input.mappings.map(toParamProfileMappingDto),
  }
}

export function toParamProfileCloneDto(input: ParamProfileCloneInput): ParamProfileCloneWriteDto {
  return { name: input.name, description: input.description }
}

export function toApiScopeOverridesDto(
  input: ApiScopeOverridesInput
): ApiScopeOverridesWriteDto {
  return {
    algorithm_type: input.algorithmType,
    api_params: input.params.map(toParamProfileParamDto),
    mappings: input.mappings.map(toParamProfileMappingDto),
  }
}

/** 绑定 / 解绑（profile_id = null 表示解绑） */
export function toParamProfileBindDto(profileId: number | null): { profile_id: number | null } {
  return { profile_id: profileId }
}

/** 供组件直接使用的枚举归一（避免在界面层重复强转） */
export function normalizeProfileScope(value: string): ParamProfileScope {
  return isParamProfileScope(value) ? value : 'api'
}

export function normalizeProfileStatus(value: string): ParamProfileStatus {
  return isParamProfileStatus(value) ? value : 'online'
}

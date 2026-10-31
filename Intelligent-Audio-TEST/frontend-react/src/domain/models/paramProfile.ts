/**
 * 参数策略领域模型（domain 层；API 实例作用域 + 可复用参数策略）。
 *
 * 契约对照：
 * - `api_gateway/schemas/_algorithm_api_param_schemas.py`
 *   （ParamProfileSaveRequest / ParamProfileCloneRequest / ParamProfileBindRequest /
 *    ApiScopedConfigSaveRequest）；
 * - `algorithm_service/infrastructure/persistence/_param_profile_repositories.py`
 *   （profile / profile_params / profile_mappings / api_param_bindings）。
 *
 * 解析优先级（后端 config_cache）：API 实例覆盖 > 策略 > 空。
 * 本文件零外部依赖，snake_case 只允许出现在 infrastructure/dto 层。
 */

/** 策略作用域（scope：api / device；绑定到 API 实例只接受 api） */
export const PARAM_PROFILE_SCOPES = ['api', 'device'] as const
export type ParamProfileScope = (typeof PARAM_PROFILE_SCOPES)[number]

/** 策略状态（status：online / offline / draft） */
export const PARAM_PROFILE_STATUSES = ['online', 'offline', 'draft'] as const
export type ParamProfileStatus = (typeof PARAM_PROFILE_STATUSES)[number]

/** 参数方向（direction：input / output） */
export const PARAM_DIRECTIONS = ['input', 'output'] as const
export type ParamDirection = (typeof PARAM_DIRECTIONS)[number]

/** 参数类型（param_type；与 AlgorithmDeviceParamItem / AlgorithmApiParamItem 同值域） */
export const PARAM_TYPES = [
  'text',
  'audio_stream',
  'audio_file',
  'text_file',
  'rttm',
  'stm',
  'json',
] as const
export type ParamType = (typeof PARAM_TYPES)[number]

/** 转换类型（transform_type；API 映射另含 base64） */
export const PARAM_TRANSFORM_TYPES = [
  'none',
  'uppercase',
  'lowercase',
  'json_parse',
  'rttm_to_obj',
  'stm_to_obj',
  'base64',
] as const
export type ParamTransformType = (typeof PARAM_TRANSFORM_TYPES)[number]

export function isParamProfileScope(value: unknown): value is ParamProfileScope {
  return typeof value === 'string' && (PARAM_PROFILE_SCOPES as readonly string[]).includes(value)
}

export function isParamProfileStatus(value: unknown): value is ParamProfileStatus {
  return (
    typeof value === 'string' && (PARAM_PROFILE_STATUSES as readonly string[]).includes(value)
  )
}

export function isParamDirection(value: unknown): value is ParamDirection {
  return typeof value === 'string' && (PARAM_DIRECTIONS as readonly string[]).includes(value)
}

export function isParamType(value: unknown): value is ParamType {
  return typeof value === 'string' && (PARAM_TYPES as readonly string[]).includes(value)
}

export function isParamTransformType(value: unknown): value is ParamTransformType {
  return (
    typeof value === 'string' &&
    (PARAM_TRANSFORM_TYPES as readonly string[]).includes(value)
  )
}

/** 参数声明行（策略字段 / API 实例覆盖行解析结果同契约） */
export interface ParamProfileParam {
  id: number
  paramCode: string
  paramName: string | null
  label: string | null
  paramType: ParamType
  direction: ParamDirection
  required: boolean
  defaultValue: string | null
  helpText: string | null
  uiOrder: number
  hidden: boolean
  /** 输出字段响应路径（C2/INT-1747；空 = 按 param_code 取顶层键） */
  fieldPath: string | null
}

/**
 * 策略映射来源：
 * - `api`：API 输出 → 评估（scope=api 策略）；
 * - `case`：用例参数 → 设备输入 / API 输入字段；
 * - `device`：设备输出 → 评估（scope=device 策略）。
 */
export type ParamProfileMappingSource = 'api' | 'case' | 'device'

/** 映射行（source 见 ParamProfileMappingSource） */
export interface ParamProfileMapping {
  id: number
  source: ParamProfileMappingSource
  sourceDirection: ParamDirection
  sourceParam: string
  dimensionId: number | null
  dimensionName: string | null
  targetParam: string
  transformType: ParamTransformType
}

/** 策略 ↔ API 实例绑定（来自 `GET /algorithm/param-profiles` 响应的 bindings） */
export interface ParamProfileBinding {
  apiId: number
  profileId: number
}

/** 策略 ↔ 设备绑定（来自 `GET /algorithm/param-profiles` 响应的 device_bindings） */
export interface DeviceParamProfileBinding {
  deviceId: number
  profileId: number
}

/**
 * API 配置快照（策略里可复用的「非端点」配置）：
 * 协议 / 流式性 / 厂商适配器 / 音频格式 / meta（请求模板、响应解析、会话、节奏、首帧/音频帧载荷）。
 * 端点地址与密钥属于实例私有，不进快照。
 */
export interface ApiConfigSnapshot {
  protocol: string | null
  streaming: boolean | null
  vendorAdapter: string | null
  audioConfig: Record<string, unknown> | null
  meta: Record<string, unknown> | null
}

/** 可复用参数策略（列表不带 params/mappings，详情带） */
export interface ParamProfile {
  id: number
  scope: ParamProfileScope
  algorithmType: string
  name: string
  description: string | null
  status: ParamProfileStatus
  clonedFrom: number | null
  /** API 配置快照（null = 旧策略，仅参数配置） */
  config: ApiConfigSnapshot | null
  params: ParamProfileParam[]
  mappings: ParamProfileMapping[]
  createdAt: string | null
  updatedAt: string | null
}

/* ------------------------------------------------------------------ */
/* 写侧草稿（camelCase；DTO 层负责转 snake_case）                        */
/* ------------------------------------------------------------------ */

export interface ParamProfileParamDraft {
  paramCode: string
  paramName: string | null
  paramType: ParamType
  direction: ParamDirection
  required: boolean
  defaultValue: string | null
  helpText: string | null
  uiOrder: number
  hidden: boolean
  fieldPath: string | null
}

export interface ParamProfileMappingDraft {
  /** 源参数来源：api = API 输出（→ 评估）；case = 用例参数；device = 设备输出（→ 评估） */
  source: ParamProfileMappingSource
  sourceDirection: ParamDirection
  sourceParam: string
  targetParam: string
  dimensionId: number | null
  transformType: ParamTransformType
}

/** POST/PUT /algorithm/param-profiles 请求体（整份保存） */
export interface ParamProfileInput {
  scope: ParamProfileScope
  algorithmType: string
  name: string
  description: string | null
  status: ParamProfileStatus
  /** API 配置快照（新建 API 可整体套用；null = 不覆盖既有快照） */
  config?: ApiConfigSnapshot | null
  params: ParamProfileParamDraft[]
  mappings: ParamProfileMappingDraft[]
}

/** POST /algorithm/param-profiles/{id}/clone 请求体 */
export interface ParamProfileCloneInput {
  name: string
  description: string | null
}

/** PUT /algorithm/api-scope/{api_id}/overrides 请求体 */
export interface ApiScopeOverridesInput {
  algorithmType: string
  params: ParamProfileParamDraft[]
  mappings: ParamProfileMappingDraft[]
}

/** PUT /algorithm/api-scope/{api_id}/overrides 响应（各表 created / updated / deleted 计数） */
export interface ApiScopeOverridesResult {
  paramsCreated: number
  paramsUpdated: number
  paramsDeleted: number
  mappingsCreated: number
  mappingsUpdated: number
  mappingsDeleted: number
}

/** PUT /algorithm/api-scope/{api_id}/binding 响应 */
export interface ApiScopeBinding {
  apiId: number
  profileId: number | null
}

/* ------------------------------------------------------------------ */
/* 展示文案（枚举 → 中文；两个特性域共用，避免各处重复硬编码）            */
/* ------------------------------------------------------------------ */

export const PARAM_TYPE_LABEL: Record<ParamType, string> = {
  text: '文本',
  audio_stream: '音频流',
  audio_file: '音频文件',
  text_file: '文本文件',
  rttm: 'RTTM标注',
  stm: 'STM标注',
  json: 'JSON结构化',
}

export const PARAM_TRANSFORM_TYPE_LABEL: Record<ParamTransformType, string> = {
  none: '不转换',
  uppercase: '转大写',
  lowercase: '转小写',
  json_parse: 'JSON 解析',
  rttm_to_obj: 'RTTM 转对象',
  stm_to_obj: 'STM 转对象',
  base64: 'Base64 解码',
}

export const PARAM_PROFILE_SCOPE_LABEL: Record<ParamProfileScope, string> = {
  api: 'API',
  device: '设备',
}

export const PARAM_PROFILE_STATUS_LABEL: Record<ParamProfileStatus, string> = {
  online: '上线',
  offline: '下线',
  draft: '草稿',
}

export const PARAM_DIRECTION_LABEL: Record<ParamDirection, string> = {
  input: '输入',
  output: '输出',
}

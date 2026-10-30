/**
 * 参数策略 API（infrastructure/api 层；T4.3 / T4.4 策略半边）。
 *
 * 端点（api_gateway/routes/algorithm_bp.py:111-149）：
 * - GET    /algorithm/param-profiles                    （algorithm:read）
 * - POST   /algorithm/param-profiles                    （algorithm:param_manage）
 * - GET    /algorithm/param-profiles/{id}               （algorithm:read）
 * - PUT    /algorithm/param-profiles/{id}               （algorithm:param_manage）
 * - DELETE /algorithm/param-profiles/{id}               （algorithm:param_manage）
 * - POST   /algorithm/param-profiles/{id}/clone         （algorithm:param_manage）
 * - PUT    /algorithm/api-scope/{api_id}/binding        （algorithm:param_manage）
 * - PUT    /algorithm/api-scope/{api_id}/overrides      （algorithm:param_manage）
 *
 * 错误统一抛 ApiError（client 层已按 { success, code, message, detail } 归一）。
 */
import type {
  ApiScopeOverridesInput,
  ApiScopeOverridesResult,
  ApiScopeBinding,
  ParamProfile,
  ParamProfileBinding,
  ParamProfileCloneInput,
  ParamProfileInput,
} from '@/domain/models/paramProfile'
import { apiClient } from '@/infrastructure/api/client'
import {
  toApiScopeOverridesDto,
  toParamProfile,
  toParamProfileBindDto,
  toParamProfileBindingList,
  toParamProfileCloneDto,
  toParamProfileDto,
  toParamProfileList,
} from '@/infrastructure/dto/param-profile.dto'

const PARAM_PROFILES_PATH = '/algorithm/param-profiles'
const API_SCOPE_PATH = '/algorithm/api-scope'

/** 列表响应（策略 + 这些策略的 API 绑定，同一响应返回） */
export interface ParamProfileListResult {
  profiles: ParamProfile[]
  bindings: ParamProfileBinding[]
}

function profilePath(profileId: number): string {
  return `${PARAM_PROFILES_PATH}/${profileId}`
}

function scopePath(apiId: number, action: 'binding' | 'overrides'): string {
  return `${API_SCOPE_PATH}/${apiId}/${action}`
}

interface ApiScopeBindingDto {
  api_id?: unknown
  profile_id?: unknown
}

interface ApiScopeOverridesResultDto {
  params_created?: unknown
  params_updated?: unknown
  params_deleted?: unknown
  mappings_created?: unknown
  mappings_updated?: unknown
  mappings_deleted?: unknown
}

function count(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

/** 策略列表（按算法类型 / 作用域过滤；空参数 = 全部）；含策略的 API 绑定 */
export async function listProfiles(
  algorithmType?: string,
  scope?: string
): Promise<ParamProfileListResult> {
  const payload = await apiClient.get<unknown>(PARAM_PROFILES_PATH, {
    params: { algorithm_type: algorithmType, scope },
  })
  return {
    profiles: toParamProfileList(payload),
    bindings: toParamProfileBindingList(payload),
  }
}

export async function getProfile(profileId: number): Promise<ParamProfile> {
  const payload = await apiClient.get<unknown>(profilePath(profileId))
  return toParamProfile(payload)
}

export async function createProfile(input: ParamProfileInput): Promise<ParamProfile> {
  const payload = await apiClient.post<unknown>(PARAM_PROFILES_PATH, toParamProfileDto(input))
  return toParamProfile(payload)
}

export async function updateProfile(
  profileId: number,
  input: ParamProfileInput
): Promise<ParamProfile> {
  const payload = await apiClient.put<unknown>(profilePath(profileId), toParamProfileDto(input))
  return toParamProfile(payload)
}

/** 软删除；data = boolean（false = 策略不存在或已删除） */
export async function deleteProfile(profileId: number): Promise<boolean> {
  const payload = await apiClient.delete<unknown>(profilePath(profileId))
  return payload === true
}

export async function cloneProfile(
  profileId: number,
  input: ParamProfileCloneInput
): Promise<ParamProfile> {
  const payload = await apiClient.post<unknown>(
    `${profilePath(profileId)}/clone`,
    toParamProfileCloneDto(input)
  )
  return toParamProfile(payload)
}

/** API 实例绑定策略；profileId = null 解绑 */
export async function bindApiProfile(
  apiId: number,
  profileId: number | null
): Promise<ApiScopeBinding> {
  const payload = await apiClient.put<unknown>(
    scopePath(apiId, 'binding'),
    toParamProfileBindDto(profileId)
  )
  const dto = (payload ?? {}) as ApiScopeBindingDto
  return {
    apiId: dto.api_id == null ? apiId : count(dto.api_id),
    profileId: dto.profile_id == null ? null : count(dto.profile_id),
  }
}

/** API 实例覆盖行整份保存（不碰策略行；只动 api_id 作用域） */
export async function saveApiScopeOverrides(
  apiId: number,
  input: ApiScopeOverridesInput
): Promise<ApiScopeOverridesResult> {
  const payload = await apiClient.put<unknown>(
    scopePath(apiId, 'overrides'),
    toApiScopeOverridesDto(input)
  )
  const dto = (payload ?? {}) as ApiScopeOverridesResultDto
  return {
    paramsCreated: count(dto.params_created),
    paramsUpdated: count(dto.params_updated),
    paramsDeleted: count(dto.params_deleted),
    mappingsCreated: count(dto.mappings_created),
    mappingsUpdated: count(dto.mappings_updated),
    mappingsDeleted: count(dto.mappings_deleted),
  }
}

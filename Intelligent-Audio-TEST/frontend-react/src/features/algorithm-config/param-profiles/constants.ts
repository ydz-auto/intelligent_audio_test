/**
 * 参数策略表单行选项（features/algorithm-config/param-profiles）。
 * 枚举值来自 domain/models/paramProfile，这里只做 Select 需要的 label 文案。
 */
import {
  PARAM_PROFILE_SCOPE_LABEL,
  PARAM_PROFILE_SCOPES,
  PARAM_PROFILE_STATUS_LABEL,
  PARAM_PROFILE_STATUSES,
  PARAM_TRANSFORM_TYPE_LABEL,
  PARAM_TRANSFORM_TYPES,
  PARAM_TYPE_LABEL,
  PARAM_TYPES,
} from '@/domain/models/paramProfile'

export const PARAM_TYPE_OPTIONS = PARAM_TYPES.map((value) => ({
  value,
  label: PARAM_TYPE_LABEL[value],
}))

export const TRANSFORM_TYPE_OPTIONS = PARAM_TRANSFORM_TYPES.map((value) => ({
  value,
  label: PARAM_TRANSFORM_TYPE_LABEL[value],
}))

export const PARAM_PROFILE_SCOPE_OPTIONS = PARAM_PROFILE_SCOPES.map((value) => ({
  value,
  label: PARAM_PROFILE_SCOPE_LABEL[value],
}))

export const PARAM_PROFILE_STATUS_OPTIONS = PARAM_PROFILE_STATUSES.map((value) => ({
  value,
  label: PARAM_PROFILE_STATUS_LABEL[value],
}))

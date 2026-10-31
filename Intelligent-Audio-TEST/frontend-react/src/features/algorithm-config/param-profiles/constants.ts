/**
 * 参数策略表单行选项（features/algorithm-config/param-profiles）。
 * 枚举值来自 domain/models/paramProfile，这里只做 Select 需要的 label 文案。
 */
import {
  PARAM_DIRECTION_LABEL,
  PARAM_DIRECTIONS,
  PARAM_MAPPING_SOURCE_LABEL,
  PARAM_PROFILE_MAPPING_SOURCES,
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

export const PARAM_DIRECTION_OPTIONS = PARAM_DIRECTIONS.map((value) => ({
  value,
  label: PARAM_DIRECTION_LABEL[value],
}))

/** 映射来源（api = API 输出 / case = 用例参数 / device = 设备输出） */
export const PARAM_MAPPING_SOURCE_OPTIONS = PARAM_PROFILE_MAPPING_SOURCES.map((value) => ({
  value,
  label: PARAM_MAPPING_SOURCE_LABEL[value],
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

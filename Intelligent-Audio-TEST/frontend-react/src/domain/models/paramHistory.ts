/**
 * 参数变更历史（设备 / API 参数与映射的版本快照）。
 *
 * 后端：`GET /algorithm/param-history`、`POST /algorithm/param-history/{id}/restore`
 * （api_gateway/application/services/algorithm/param_history_service.py）。
 * 快照只含该作用域的覆盖行，回滚语义 = 把覆盖行整份恢复成该版本。
 * 本文件零依赖，snake_case 只允许出现在 infrastructure/dto 层。
 */

export const PARAM_HISTORY_SCOPES = ['api', 'device'] as const
export type ParamHistoryScope = (typeof PARAM_HISTORY_SCOPES)[number]

export const PARAM_HISTORY_ACTIONS = ['save', 'restore'] as const
export type ParamHistoryAction = (typeof PARAM_HISTORY_ACTIONS)[number]

export const PARAM_HISTORY_ACTION_LABEL: Record<ParamHistoryAction, string> = {
  save: '保存',
  restore: '回滚',
}

export interface ParamHistoryVersion {
  id: number
  /** 同作用域内自增版本号 */
  version: number
  action: ParamHistoryAction
  operator: string | null
  /** ISO 时间字符串（后端下发） */
  createdAt: string | null
  paramCount: number
  mappingCount: number
}

export interface ParamHistoryRestoreResult {
  paramsCreated?: number
  paramsUpdated?: number
  paramsDeleted?: number
  mappingsCreated?: number
  mappingsUpdated?: number
  mappingsDeleted?: number
  paramsRestored?: number
  mappingsRestored?: number
}

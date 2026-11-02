/**
 * 参数变更历史 API（infrastructure/api 层）。
 *
 * 端点（api_gateway/routes/algorithm_bp.py）：
 * - GET  /algorithm/param-history?scope=&scope_id=&algorithm_type=   （algorithm:read）
 * - POST /algorithm/param-history/{history_id}/restore              （algorithm:param_manage）
 */
import type {
  ParamHistoryRestoreResult,
  ParamHistoryScope,
  ParamHistoryVersion,
} from '@/domain/models/paramHistory'
import { apiClient } from '@/infrastructure/api/client'
import { toParamHistoryVersions } from '@/infrastructure/dto/param-history.dto'

const PARAM_HISTORY_PATH = '/algorithm/param-history'

/** 某作用域的版本列表（id 倒序，最多 50 条） */
export async function fetchParamHistory(
  scope: ParamHistoryScope,
  scopeId: number,
  algorithmType: string
): Promise<ParamHistoryVersion[]> {
  const payload = await apiClient.get<unknown>(PARAM_HISTORY_PATH, {
    params: {
      scope,
      scope_id: scopeId,
      algorithm_type: algorithmType,
    },
  })
  return toParamHistoryVersions(payload)
}

/** 回滚到指定版本（后端按版本快照重建该作用域的覆盖行） */
export async function restoreParamHistory(
  historyId: number
): Promise<ParamHistoryRestoreResult> {
  const dto = await apiClient.post<ParamHistoryRestoreResult>(
    `${PARAM_HISTORY_PATH}/${historyId}/restore`,
    {}
  )
  return dto ?? {}
}

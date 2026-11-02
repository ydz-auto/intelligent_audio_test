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

/** 回滚结果归一（INT-2341） */
function count(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

/**
 * 回滚回执口径（后端 `param_history_service.restore`）：
 * - API 作用域：`{ paramsRestored, mappingsRestored, detail: { params_created/updated… } }`
 *   （快照整份写回，只有总数）；
 * - 设备作用域：`{ paramsCreated, paramsUpdated, paramsDeleted, mappings* }`。
 * 两种都归一到同一模型；snake_case 只在本层出现。
 */
function toRestoreResult(payload: unknown): ParamHistoryRestoreResult {
  const dto = (payload ?? {}) as Record<string, unknown>
  const detail = (dto.detail ?? {}) as Record<string, unknown>
  const pick = (...values: unknown[]): number | undefined => {
    for (const value of values) {
      const parsed = count(value)
      if (parsed !== undefined) return parsed
    }
    return undefined
  }
  return {
    paramsRestored: pick(dto.paramsRestored, dto.params_restored),
    mappingsRestored: pick(dto.mappingsRestored, dto.mappings_restored),
    paramsCreated: pick(dto.paramsCreated, dto.params_created, detail.params_created),
    paramsUpdated: pick(dto.paramsUpdated, dto.params_updated, detail.params_updated),
    paramsDeleted: pick(dto.paramsDeleted, dto.params_deleted, detail.params_deleted),
    mappingsCreated: pick(dto.mappingsCreated, dto.mappings_created, detail.mappings_created),
    mappingsUpdated: pick(dto.mappingsUpdated, dto.mappings_updated, detail.mappings_updated),
    mappingsDeleted: pick(dto.mappingsDeleted, dto.mappings_deleted, detail.mappings_deleted),
  }
}

/** 回滚到指定版本（后端按版本快照重建该作用域的覆盖行） */
export async function restoreParamHistory(
  historyId: number
): Promise<ParamHistoryRestoreResult> {
  const payload = await apiClient.post<unknown>(`${PARAM_HISTORY_PATH}/${historyId}/restore`, {})
  return toRestoreResult(payload)
}

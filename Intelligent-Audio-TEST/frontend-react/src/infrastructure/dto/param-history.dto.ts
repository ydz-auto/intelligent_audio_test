/**
 * 参数变更历史 DTO（infrastructure/dto 层）。
 *
 * snake_case ↔ camelCase 只在本层做；页面只见 Domain `ParamHistoryVersion`。
 */
import {
  PARAM_HISTORY_ACTIONS,
  type ParamHistoryAction,
  type ParamHistoryVersion,
} from '@/domain/models/paramHistory'

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null
    ? (value as Record<string, unknown>)
    : {}
}

function num(value: unknown): number | null {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function nullableStr(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null
}

function toAction(value: unknown): ParamHistoryAction {
  return PARAM_HISTORY_ACTIONS.includes(value as ParamHistoryAction)
    ? (value as ParamHistoryAction)
    : 'save'
}

/** `{ items: [...] }` 或裸数组 → Domain 版本列表 */
export function toParamHistoryVersions(payload: unknown): ParamHistoryVersion[] {
  const rows = Array.isArray(payload)
    ? payload
    : Array.isArray(asRecord(payload).items)
      ? (asRecord(payload).items as unknown[])
      : []
  return rows.map((raw) => {
    const row = asRecord(raw)
    return {
      id: num(row.id) ?? 0,
      version: num(row.version) ?? 0,
      action: toAction(row.action),
      operator: nullableStr(row.operator),
      createdAt: nullableStr(row.created_at ?? row.createdAt),
      paramCount: num(row.param_count ?? row.paramCount) ?? 0,
      mappingCount: num(row.mapping_count ?? row.mappingCount) ?? 0,
    }
  })
}

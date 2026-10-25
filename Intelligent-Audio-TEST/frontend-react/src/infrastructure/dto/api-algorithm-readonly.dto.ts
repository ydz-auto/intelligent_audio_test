/**
 * API 编辑弹窗只读页签 DTO（infrastructure/dto 层；INT-1778，母卡 INT-1750 C5-2）。
 *
 * 两个算法类型级读接口（snake_case ↔ camelCase 只在本层做）：
 * - `GET /algorithm/params?algorithm_type=X&param_type=api`
 *   → 输出字段页签数据源（只取 direction=output 行；同时是 C0 兜底口径的判定依据）；
 * - `GET /algorithm/mappings?algorithm_type=X&source_type=api`
 *   → 映射页签**唯一**数据源。后端 `ParamMapping.to_dict()` 只下发 PO 列（无 dimension_name），
 *   维度名由调用侧按 dimension_id 补齐。
 *
 * 映射行复用 algorithm-config.dto 的 toParamMapping（同一 ParamMappingItem 契约）；
 * 参数行复用 toDeviceApiParam 再补 C2（INT-1747）的 field_path。
 */
import type { AlgorithmApiMapping, AlgorithmApiParam } from '@/domain/models/apiConfig'
import {
  toDeviceApiParam,
  toParamMapping,
} from '@/infrastructure/dto/algorithm-config.dto'

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null
    ? (value as Record<string, unknown>)
    : {}
}

function nullableStr(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null
}

/** GET /algorithm/params（INT-297 统一分页信封；只消费 items） */
export interface AlgorithmApiParamListDto {
  items?: unknown[]
  total?: number
}

/** GET /algorithm/mappings（同上） */
export interface AlgorithmApiMappingListDto {
  items?: unknown[]
  total?: number
}

/** API 参数行 → Domain AlgorithmApiParam（含 field_path） */
export function toAlgorithmApiParam(raw: unknown): AlgorithmApiParam {
  const r = asRecord(raw)
  return {
    ...toDeviceApiParam(raw),
    fieldPath: nullableStr(r.field_path),
  }
}

/** 映射行 → Domain AlgorithmApiMapping */
export function toAlgorithmApiMapping(raw: unknown): AlgorithmApiMapping {
  return toParamMapping(raw)
}

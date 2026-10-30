/**
 * API 编辑弹窗「参数配置」页签 DTO（infrastructure/dto 层；T4.2）。
 *
 * 两个 API 实例作用域读接口（snake_case ↔ camelCase 只在本层做）：
 * - `GET /algorithm/params?algorithm_type=X&param_type=api&api_id=Y`
 *   → 字段行数据源（后端 `config_cache.get_api_params` = 策略声明 + 本 API 覆盖行，
 *   覆盖优先；算法类型级默认层已废弃，`api_id` 必填）；
 * - `GET /algorithm/mappings?algorithm_type=X&source_type=evaluation&api_id=Y`
 *   → 映射行数据源。API 输出映射带 dimension_id，后端 `_serialize_mappings` 归入
 *   evaluation 桶，`source_type=api` 结构性为空；本层再按 `source === 'api'` 过滤。
 *
 * 后端 `get_api_params` / `_serialize_params` 的行键是 `code / name / type`
 * （不是 `param_code / param_name / param_type`），这里统一归一再转 Domain。
 * 映射行复用 algorithm-config.dto 的 toParamMapping（同一 ParamMappingItem 契约）。
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

/**
 * `/algorithm/params`、`/algorithm/mappings` 的 data 兼容两种形态：
 * 统一分页信封 `{ items, total }`（旧契约）与裸数组（现有 gRPC 返回值）。
 */
export function rowsFromPayload(payload: unknown): unknown[] {
  if (Array.isArray(payload)) return payload
  const items = asRecord(payload).items
  return Array.isArray(items) ? items : []
}

/** API 参数行 → Domain AlgorithmApiParam（兼容 code/name/type 旧键） */
export function toAlgorithmApiParam(raw: unknown): AlgorithmApiParam {
  const r = asRecord(raw)
  const normalized = {
    ...r,
    param_code: r.param_code ?? r.code ?? '',
    param_name: r.param_name ?? r.name ?? null,
    param_type: r.param_type ?? r.type ?? 'text',
  }
  const param = toDeviceApiParam(normalized)
  return {
    ...param,
    direction: param.direction === 'output' ? 'output' : 'input',
    fieldPath: nullableStr(r.field_path),
  }
}

/** 映射行 → Domain AlgorithmApiMapping */
export function toAlgorithmApiMapping(raw: unknown): AlgorithmApiMapping {
  return toParamMapping(raw)
}

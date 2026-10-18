/**
 * 算法选项 DTO（infrastructure/dto 层；snake_case↔camelCase 唯一转换层）。
 * 对照 GET /api/v1/algorithm/options（algorithm_bp.py:165）实际契约（实测 2026-10-17）：
 * data: { algorithms: [{ value, name, group_id, group_name, icon }] }——仅在线算法，
 * value = 算法类型码（业务列表 algorithm_type 过滤参数，与 MOCK_ALGORITHMS 的 id 对齐）。
 */
import type { AlgorithmOption } from '@/domain/models/algorithm'

export interface AlgorithmOptionDto {
  /** 算法类型码（全局过滤值；切换器选中即写全局 store） */
  value: string
  /** 算法名称（下拉展示） */
  name: string
  group_id?: number | null
  group_name?: string | null
  icon?: string | null
}

export interface AlgorithmOptionsResultDto {
  algorithms: AlgorithmOptionDto[]
}

/** options 项 → Domain AlgorithmOption（id 落 value 码；group_name 作副行展示） */
export function toAlgorithmOption(raw: AlgorithmOptionDto): AlgorithmOption {
  return {
    id: raw.value,
    name: raw.name,
    version: '',
    description: raw.group_name ?? '',
    enabled: true,
  }
}

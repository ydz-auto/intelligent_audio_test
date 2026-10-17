/**
 * 算法选项 DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换层）。
 * 对照 GET /api/v1/algorithm/options（algorithm_bp.py:165-167，algorithm:read）
 * 响应 data 契约：{ options: [{ id, name, type }] }（gRPC GetAlgorithmOptions
 * servicers.py:325-341，仅在线算法 ListAlgorithmDefinitionsQuery(status='online')）。
 * snake→camel 转换收敛在本文件，application/domain 只见 camelCase。
 */
import type { AlgorithmSwitchOption } from '@/domain/models/algorithm'

/** 后端算法选项项（snake_case wire 契约：type=算法类型码，即全局算法 store 的 value） */
export interface AlgorithmOptionItemDto {
  id: number
  name: string
  type: string
}

/** GET /algorithm/options 响应 data 信封 */
export interface AlgorithmOptionsResultDto {
  options: AlgorithmOptionItemDto[]
}

/** snake_case → camelCase Domain（value=type，与 useAlgorithmStore.algorithmId 同源） */
export function toAlgorithmOption(
  raw: AlgorithmOptionItemDto
): AlgorithmSwitchOption {
  return {
    value: raw.type,
    name: raw.name,
  }
}

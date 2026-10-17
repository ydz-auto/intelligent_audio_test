/**
 * 算法选项 DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换层）。
 * 对照 GET /api/v1/algorithm/options（algorithm_bp.py:165-167，algorithm:read）
 * 响应 data 契约（实测）：{ algorithms: [{ value, name, group_id?, group_name?, icon? }] }
 * （gRPC GetAlgorithmOptions servicers.py:325-341，仅在线算法
 * ListAlgorithmDefinitionsQuery(status='online')；value=算法类型码如 voice_llm，
 * 即全局算法 store 的 algorithmId 同源值）。
 * snake→camel 转换收敛在本文件，application/domain 只见 camelCase。
 */
import type { AlgorithmSwitchOption } from '@/domain/models/algorithm'

/** 后端算法选项项（snake_case wire 契约：value=算法类型码，即全局算法 store 的 value） */
export interface AlgorithmOptionItemDto {
  value: string
  name: string
  group_id?: number | null
  group_name?: string | null
  icon?: string | null
}

/** GET /algorithm/options 响应 data 信封 */
export interface AlgorithmOptionsResultDto {
  algorithms: AlgorithmOptionItemDto[]
}

/** snake_case → camelCase Domain（value 与 useAlgorithmStore.algorithmId 同源） */
export function toAlgorithmOption(
  raw: AlgorithmOptionItemDto
): AlgorithmSwitchOption {
  return {
    value: raw.value,
    name: raw.name,
  }
}

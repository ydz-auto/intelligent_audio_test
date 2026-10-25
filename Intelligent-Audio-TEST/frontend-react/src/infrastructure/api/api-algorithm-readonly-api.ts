/**
 * API 编辑弹窗只读页签数据源（infrastructure/api 层；INT-1778，母卡 INT-1750 C5-2 §2.4 / §2.5）。
 *
 * 端点（api_gateway/routes/algorithm_bp.py，均需 `algorithm:read`）：
 * - `GET /algorithm/params?algorithm_type=X&param_type=api` → 算法类型的 API 参数声明；
 *   输出字段页签取 `direction=output` 行，同时「没有 output 行」就是 C0（INT-1745）
 *   兜底口径的判定依据（同一次请求，口径唯一）。
 * - `GET /algorithm/mappings?algorithm_type=X&source_type=api` → 映射页签唯一数据源。
 *   禁用 `GET /algorithm/definitions/{type}` 的 `mappings.api`：`source='api'` 行带
 *   dimension_id，会被 `algorithm_crud_service._serialize_mappings` 归进 `evaluation` 桶，
 *   `mappings.api` 结构性为空（页签恒空）。
 *
 * 后端怪癖（本卡不改后端）：网关把 `source_type` 透传进 gRPC ListMappingsRequest，
 * 但 algorithm_service `_ParamQueryMixin.ListMappings` 只按 algorithm_type 组查询，
 * 过滤不到 source —— 所以本层拿到结果后再按 `source === 'api'` 过滤一次。
 */
import type { AlgorithmApiMapping, AlgorithmApiParam } from '@/domain/models/apiConfig'
import { apiClient } from '@/infrastructure/api/client'
import {
  toAlgorithmApiMapping,
  toAlgorithmApiParam,
  type AlgorithmApiMappingListDto,
  type AlgorithmApiParamListDto,
} from '@/infrastructure/dto/api-algorithm-readonly.dto'

/** 算法类型的 API 参数声明全量（input + output；调用方自行按 direction 过滤） */
export async function fetchAlgorithmApiParams(
  algorithmType: string
): Promise<AlgorithmApiParam[]> {
  const dto = await apiClient.get<AlgorithmApiParamListDto>('/algorithm/params', {
    params: { algorithm_type: algorithmType, param_type: 'api' },
  })
  return (dto?.items ?? []).map(toAlgorithmApiParam)
}

/** 算法类型 `source='api'` 的参数映射（已按 source 过滤，见文件头后端怪癖） */
export async function fetchAlgorithmApiMappings(
  algorithmType: string
): Promise<AlgorithmApiMapping[]> {
  const dto = await apiClient.get<AlgorithmApiMappingListDto>('/algorithm/mappings', {
    params: { algorithm_type: algorithmType, source_type: 'api' },
  })
  return (dto?.items ?? [])
    .map(toAlgorithmApiMapping)
    .filter((mapping) => mapping.source === 'api')
}

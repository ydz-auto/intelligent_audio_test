/**
 * API 编辑弹窗「参数配置」页签数据源（infrastructure/api 层；T4.2）。
 *
 * 端点（api_gateway/routes/algorithm_bp.py / AlgorithmQueryService）：
 * - `GET /algorithm/params?algorithm_type=X&param_type=api&api_id=Y`
 *   → 该 API 的字段行（策略 + 实例覆盖解析结果；后端强制要求 api_id，缺省 400）；
 * - `GET /algorithm/mappings?algorithm_type=X&source_type=evaluation&api_id=Y`
 *   → 按 API 作用域解析的映射行；API 输出映射带 dimension_id 会落在 evaluation 桶，
 *   因此这里用 evaluation 作为组件类型，再按 `source === 'api'` 过滤（见 DTO 文件头）。
 *
 * 降级：403（缺 algorithm:read）原样抛 ApiError，由 composable 判定为 forbidden。
 */
import type { AlgorithmApiMapping, AlgorithmApiParam } from '@/domain/models/apiConfig'
import { apiClient } from '@/infrastructure/api/client'
import {
  rowsFromPayload,
  toAlgorithmApiMapping,
  toAlgorithmApiParam,
} from '@/infrastructure/dto/api-algorithm-readonly.dto'

/** API 实例的字段行（input + output；调用方按 direction 过滤） */
export async function fetchAlgorithmApiParams(
  algorithmType: string,
  apiId: number
): Promise<AlgorithmApiParam[]> {
  const payload = await apiClient.get<unknown>('/algorithm/params', {
    params: { algorithm_type: algorithmType, param_type: 'api', api_id: apiId },
  })
  return rowsFromPayload(payload).map(toAlgorithmApiParam)
}

/** API 实例 `source='api'` 的参数映射（已按 source 过滤） */
export async function fetchAlgorithmApiMappings(
  algorithmType: string,
  apiId: number
): Promise<AlgorithmApiMapping[]> {
  const payload = await apiClient.get<unknown>('/algorithm/mappings', {
    params: { algorithm_type: algorithmType, source_type: 'evaluation', api_id: apiId },
  })
  return rowsFromPayload(payload)
    .map(toAlgorithmApiMapping)
    .filter((mapping) => mapping.source === 'api')
}

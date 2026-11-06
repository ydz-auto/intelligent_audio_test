/**
 * API 编辑弹窗「参数配置」页签数据源（infrastructure/api 层；T4.2）。
 *
 * 端点（api_gateway/routes/algorithm_bp.py / AlgorithmQueryService）：
 * - `GET /algorithm/params?algorithm_type=X&param_type=api&api_id=Y`
 *   → 该 API 的字段行（策略 + 实例覆盖解析结果；后端强制要求 api_id，缺省 400）；
 * - `GET /algorithm/mappings?algorithm_type=X&source_type=evaluation&api_id=Y`
 *   → 按 API 作用域解析的映射行；API 输出映射带 dimension_id 会落在 evaluation 桶，
 *   因此这里用 evaluation 作为组件类型，返回「算法级 + 本 API 级」原始集合；
 *   按来源分桶在 application 层（`useApiParamConfig`），本层不按 source 过滤
 *   （否则 device / case+输出行被丢掉，整份保存时会被软删，INT-2281）。
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

/**
 * API 实例作用域映射行（原始集合，不在这里过滤）。
 *
 * 读侧返回「算法级 + 本 API 级」合并结果，应用层再按用途分桶：
 * API 输出映射、用例参数输入映射、以及页签不展示但保存时必须原值透传的
 * 本 API 其余来源行（api_id 命中）。在这一层按 source 过滤会把 device 行
 * 直接丢掉，整份保存时它们就被软删（INT-2281）。
 */
export async function fetchAlgorithmApiMappings(
  algorithmType: string,
  apiId: number
): Promise<AlgorithmApiMapping[]> {
  const payload = await apiClient.get<unknown>('/algorithm/mappings', {
    params: { algorithm_type: algorithmType, source_type: 'evaluation', api_id: apiId },
  })
  return rowsFromPayload(payload).map(toAlgorithmApiMapping)
}

/** 算法类型下的用例参数（`GET /algorithm/case-params`；供输入映射选源） */
export async function fetchAlgorithmCaseParams(
  algorithmType: string
): Promise<AlgorithmApiParam[]> {
  const payload = await apiClient.get<unknown>('/algorithm/case-params', {
    params: { algorithm_type: algorithmType },
  })
  return rowsFromPayload(payload).map(toAlgorithmApiParam)
}

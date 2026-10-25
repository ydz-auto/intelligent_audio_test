/**
 * API 编辑弹窗只读页签（输出字段 / 映射）查询编排（application 层；INT-1778）。
 *
 * - 两个数据源都是**算法类型作用域**（母卡 INT-1750 §四.3）：只在选了关联算法、且用户切到
 *   相关页签时才请求，避免每次打开弹窗多发两个 GET。
 * - `algorithm:read` 缺失（编辑既有 API 时 403）→ 页签降级为「无权查看算法配置」，
 *   查询错误不外抛、不阻断其它页签保存（母卡 §3.3）。
 * - `/algorithm/mappings` 不下发 dimension_name，这里按 dimension_id 用评估维度全量补名；
 *   维度接口不可达时保持 null（界面显示「—」），不影响映射行展示。
 */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import type { AlgorithmApiMapping, AlgorithmApiParam } from '@/domain/models/apiConfig'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  fetchAlgorithmApiMappings,
  fetchAlgorithmApiParams,
} from '@/infrastructure/api/api-algorithm-readonly-api'
import { fetchEvaluationDimensions } from '@/infrastructure/api/evaluation-api'

/** 只读页签的取数状态（界面据此渲染加载 / 无权 / 错误 / 空态） */
export type ReadonlyQueryState = 'idle' | 'loading' | 'ready' | 'forbidden' | 'error'

/** 403 = 缺 `algorithm:read`（母卡 §3.3 降级口径） */
export function isForbiddenError(error: unknown): boolean {
  return error instanceof ApiError && error.httpStatus === 403
}

function queryState(
  enabled: boolean,
  hasData: boolean,
  error: unknown,
  isFetching: boolean
): ReadonlyQueryState {
  if (!enabled) return 'idle'
  if (error) return isForbiddenError(error) ? 'forbidden' : 'error'
  if (isFetching || !hasData) return 'loading'
  return 'ready'
}

export interface AlgorithmApiParamsResult {
  state: ReadonlyQueryState
  /** `direction=output` 的声明行（输出字段页签数据源） */
  outputParams: AlgorithmApiParam[]
  /**
   * C0（INT-1745）判定：该算法类型是否**没有**任何 output 声明
   * （同一次 `/algorithm/params` 请求为唯一依据）。未知状态返回 null。
   */
  noOutputDeclared: boolean | null
}

/** 算法类型 API 参数声明（输出字段页签 + 响应解析页签的 C0 判定） */
export function useAlgorithmApiParams(
  algorithmType: string,
  enabled: boolean
): AlgorithmApiParamsResult {
  const active = enabled && Boolean(algorithmType)
  const query = useQuery({
    queryKey: ['test-execution', 'api-dialog', 'algorithm-api-params', algorithmType],
    queryFn: () => fetchAlgorithmApiParams(algorithmType),
    enabled: active,
    // 0 = 每次打开弹窗都取最新声明：算法配置可能在另一个页签里刚改过
    // （「新增输出字段 → 重开本弹窗可见」的跨页动线），缓存会显示旧结果
    staleTime: 0,
    // 403 是权限结论而不是抖动，重试只会把降级提示拖慢
    retry: false,
  })

  const outputParams = useMemo(
    () => (query.data ?? []).filter((param) => param.direction === 'output'),
    [query.data]
  )
  const state = queryState(active, query.data != null, query.error, query.isFetching)
  return {
    state,
    outputParams,
    // 只有真正拿到数据才给判定，否则按「未知」处理，不臆造兜底结论
    noOutputDeclared: state === 'ready' ? outputParams.length === 0 : null,
  }
}

export interface AlgorithmApiMappingsResult {
  state: ReadonlyQueryState
  /** `source='api'` 的映射行（维度名已按 dimension_id 补齐，取不到为 null） */
  rows: AlgorithmApiMapping[]
}

/** 算法类型 `source='api'` 的参数映射（映射页签唯一数据源） */
export function useAlgorithmApiMappings(
  algorithmType: string,
  enabled: boolean
): AlgorithmApiMappingsResult {
  const active = enabled && Boolean(algorithmType)
  const query = useQuery({
    queryKey: ['test-execution', 'api-dialog', 'algorithm-api-mappings', algorithmType],
    queryFn: () => fetchAlgorithmApiMappings(algorithmType),
    enabled: active,
    // 0 = 每次打开都取最新映射（在算法配置页刚新增的行必须立刻可见）
    staleTime: 0,
    retry: false,
  })

  const missingNames = (query.data ?? []).some(
    (row) => row.dimensionId != null && !row.dimensionName
  )
  const dimensionsQuery = useQuery({
    queryKey: ['evaluation', 'dimensions'],
    queryFn: fetchEvaluationDimensions,
    enabled: active && missingNames,
    staleTime: 60_000,
    retry: false,
  })

  const rows = useMemo(() => {
    const data = query.data ?? []
    if (!dimensionsQuery.data) return data
    const nameById = new Map(dimensionsQuery.data.map((d) => [Number(d.id), d.name]))
    return data.map((row) =>
      row.dimensionId != null && !row.dimensionName
        ? { ...row, dimensionName: nameById.get(row.dimensionId) ?? null }
        : row
    )
  }, [query.data, dimensionsQuery.data])

  return {
    state: queryState(active, query.data != null, query.error, query.isFetching),
    rows,
  }
}

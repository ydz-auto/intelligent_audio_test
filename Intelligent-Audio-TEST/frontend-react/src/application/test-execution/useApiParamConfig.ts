/**
 * API 编辑弹窗「参数配置」页签查询编排（application 层；T4.2 / T4.4）。
 *
 * 数据源全部是 **API 实例作用域**（算法类型级默认层已废弃）：
 * - 字段行 = 策略声明 + 本 API 覆盖行（`GET /algorithm/params?...&api_id=Y`）；
 * - 映射行 = 策略映射 + 本 API 覆盖行（`GET /algorithm/mappings?...&api_id=Y`）；
 * - 策略下拉 = 本 algorithm_type 下 scope=api 的策略列表。
 *
 * 降级口径：403（缺 `algorithm:read`）→ 页签「无权查看」，不阻断其他页签保存。
 */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import type { AlgorithmApiMapping, AlgorithmApiParam } from '@/domain/models/apiConfig'
import type { ParamProfile } from '@/domain/models/paramProfile'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  fetchAlgorithmApiMappings,
  fetchAlgorithmApiParams,
} from '@/infrastructure/api/api-algorithm-readonly-api'
import { fetchEvaluationDimensions } from '@/infrastructure/api/evaluation-api'
import { listProfiles } from '@/infrastructure/api/param-profile-api'

/** 页签取数状态（界面据此渲染加载 / 无权 / 错误 / 空态） */
export type ReadonlyQueryState = 'idle' | 'loading' | 'ready' | 'forbidden' | 'error'

/** 403 = 缺 `algorithm:read`（或策略列表无权限） */
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

/** 查询键（绑定 / 另存 / 覆盖保存后统一失效，见 api-param-config-tab） */
export const paramConfigQueryKeys = {
  scopeParams: (algorithmType: string, apiId: number | null) =>
    ['test-execution', 'api-dialog', 'api-scope-params', algorithmType, apiId] as const,
  scopeMappings: (algorithmType: string, apiId: number | null) =>
    ['test-execution', 'api-dialog', 'api-scope-mappings', algorithmType, apiId] as const,
  profiles: (algorithmType: string) =>
    ['test-execution', 'api-dialog', 'param-profiles', algorithmType] as const,
}

export interface ApiParamConfigResult {
  state: ReadonlyQueryState
  /** `direction=output` 的字段行（参数配置页签数据源） */
  outputParams: AlgorithmApiParam[]
  /** `source='api'` 的映射行（维度名已按 dimension_id 补齐） */
  mappings: AlgorithmApiMapping[]
  /**
   * C0（INT-1745）判定：该 API 是否没有任何 output 字段声明（策略 + 覆盖解析结果）。
   * 未知状态返回 null。
   */
  noOutputDeclared: boolean | null
}

/** API 实例的字段行 + 映射（参数配置页签 + 响应解析页签 C0 判定共用一次请求） */
export function useApiParamConfig(
  apiId: number | null,
  algorithmType: string,
  enabled: boolean
): ApiParamConfigResult {
  const active = enabled && Boolean(algorithmType) && apiId != null

  const paramsQuery = useQuery({
    queryKey: paramConfigQueryKeys.scopeParams(algorithmType, apiId),
    queryFn: () => fetchAlgorithmApiParams(algorithmType, apiId as number),
    enabled: active,
    // 0 = 每次打开弹窗都取最新：策略 / 覆盖可能刚在别处改过
    staleTime: 0,
    retry: false,
  })

  const mappingsQuery = useQuery({
    queryKey: paramConfigQueryKeys.scopeMappings(algorithmType, apiId),
    queryFn: () => fetchAlgorithmApiMappings(algorithmType, apiId as number),
    enabled: active,
    staleTime: 0,
    retry: false,
  })

  const outputParams = useMemo(
    () => (paramsQuery.data ?? []).filter((param) => param.direction === 'output'),
    [paramsQuery.data]
  )

  const missingNames = (mappingsQuery.data ?? []).some(
    (row) => row.dimensionId != null && !row.dimensionName
  )
  const dimensionsQuery = useQuery({
    queryKey: ['evaluation', 'dimensions'],
    queryFn: fetchEvaluationDimensions,
    enabled: active && missingNames,
    staleTime: 60_000,
    retry: false,
  })

  const mappings = useMemo(() => {
    const data = mappingsQuery.data ?? []
    if (!dimensionsQuery.data) return data
    const nameById = new Map(dimensionsQuery.data.map((d) => [Number(d.id), d.name]))
    return data.map((row) =>
      row.dimensionId != null && !row.dimensionName
        ? { ...row, dimensionName: nameById.get(row.dimensionId) ?? null }
        : row
    )
  }, [mappingsQuery.data, dimensionsQuery.data])

  const failure = paramsQuery.error ?? mappingsQuery.error
  const state = queryState(
    active,
    paramsQuery.data != null && mappingsQuery.data != null,
    failure,
    paramsQuery.isFetching || mappingsQuery.isFetching
  )

  return {
    state,
    outputParams,
    mappings,
    noOutputDeclared: state === 'ready' ? outputParams.length === 0 : null,
  }
}

export interface ParamProfileOptionsResult {
  state: ReadonlyQueryState
  /** 本算法类型下 scope=api 的策略（API 实例只能绑定 api 作用域策略） */
  profiles: ParamProfile[]
  /** 本 API 已绑定的策略 id（未绑定 / 未知 apiId = null） */
  boundProfileId: number | null
}

/** 策略下拉数据源（策略管理入口与 API 弹窗共用） */
export function useParamProfileOptions(
  algorithmType: string,
  enabled: boolean,
  apiId?: number | null
): ParamProfileOptionsResult {
  const active = enabled && Boolean(algorithmType)
  const query = useQuery({
    queryKey: paramConfigQueryKeys.profiles(algorithmType),
    queryFn: () => listProfiles(algorithmType, 'api'),
    enabled: active,
    staleTime: 0,
    retry: false,
  })

  const boundProfileId = useMemo(() => {
    if (apiId == null) return null
    const binding = (query.data?.bindings ?? []).find((item) => item.apiId === apiId)
    return binding ? binding.profileId : null
  }, [query.data, apiId])

  return {
    state: queryState(active, query.data != null, query.error, query.isFetching),
    profiles: query.data?.profiles ?? [],
    boundProfileId,
  }
}

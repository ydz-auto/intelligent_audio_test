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
import type { Dimension } from '@/domain/models/evaluationDimension'
import type { ParamProfile } from '@/domain/models/paramProfile'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  fetchAlgorithmApiMappings,
  fetchAlgorithmApiParams,
  fetchAlgorithmCaseParams,
} from '@/infrastructure/api/api-algorithm-readonly-api'
import { fetchDimensionParams } from '@/infrastructure/api/algorithm-config-api'
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
  caseParams: (algorithmType: string) =>
    ['test-execution', 'api-dialog', 'case-params', algorithmType] as const,
}

export interface ApiParamConfigResult {
  state: ReadonlyQueryState
  /** `direction=output` 的字段行（参数配置页签数据源） */
  outputParams: AlgorithmApiParam[]
  /** `direction=input` 的字段行（输入映射的目标侧） */
  inputParams: AlgorithmApiParam[]
  /** `source='api'` 的映射行（维度名已按 dimension_id 补齐） */
  mappings: AlgorithmApiMapping[]
  /** `source='case'` + `source_direction='input'`：用例参数 → API 输入字段 */
  inputMappings: AlgorithmApiMapping[]
  /** 输入映射的源候选（算法类型下的用例参数） */
  caseParams: AlgorithmApiParam[]
  /** 评估维度列表（映射行的「维度」下拉 + 维度名补齐） */
  dimensions: Dimension[]
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
  // API 输入字段（输入映射的目标侧；字段本身在「参数策略」声明）
  const inputParams = useMemo(
    () => (paramsQuery.data ?? []).filter((param) => param.direction === 'input'),
    [paramsQuery.data]
  )

  const dimensionsQuery = useQuery({
    queryKey: ['evaluation', 'dimensions'],
    queryFn: fetchEvaluationDimensions,
    // 维度下拉 + 维度名补齐共用一份：始终取（60s 缓存），不再只在缺名字时才拉
    enabled: active,
    staleTime: 60_000,
    retry: false,
  })
  const dimensions = useMemo(() => dimensionsQuery.data ?? [], [dimensionsQuery.data])

  const allMappings = useMemo(() => {
    const data = mappingsQuery.data ?? []
    if (!dimensionsQuery.data) return data
    const nameById = new Map(dimensionsQuery.data.map((d) => [Number(d.id), d.name]))
    return data.map((row) =>
      row.dimensionId != null && !row.dimensionName
        ? { ...row, dimensionName: nameById.get(row.dimensionId) ?? null }
        : row
    )
  }, [mappingsQuery.data, dimensionsQuery.data])

  // 输出映射（API 响应字段 → 评估参数）与输入映射（用例参数 → API 输入字段）分开
  const mappings = useMemo(
    () => allMappings.filter((row) => row.source === 'api'),
    [allMappings]
  )
  const inputMappings = useMemo(
    () => allMappings.filter(
      (row) => row.source === 'case' && row.sourceDirection === 'input'
    ),
    [allMappings]
  )

  // 输入映射的源候选：算法类型下的用例参数（失败不影响主流程，按空候选处理）
  const caseParamsQuery = useQuery({
    queryKey: paramConfigQueryKeys.caseParams(algorithmType),
    queryFn: () => fetchAlgorithmCaseParams(algorithmType),
    enabled: active,
    staleTime: 60_000,
    retry: false,
  })

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
    inputParams,
    mappings,
    inputMappings,
    caseParams: caseParamsQuery.data ?? [],
    dimensions,
    noOutputDeclared: state === 'ready' ? outputParams.length === 0 : null,
  }
}

/** 某个评估维度的参数列表（映射行「目标参数」下拉；随维度联动） */
export function useDimensionParams(dimensionId: number | null) {
  return useQuery({
    queryKey: ['algorithm', 'dimension-params', dimensionId],
    queryFn: () => fetchDimensionParams(dimensionId as number),
    enabled: dimensionId != null,
    staleTime: 60_000,
    retry: false,
  })
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

/**
 * 参数策略管理编排（application 层；T4.3）。
 *
 * 列表 / 详情 / 保存 / 克隆 / 删除都走 infrastructure/api/param-profile-api；
 * 本层只做查询键统一与失效，不在界面层拼供数逻辑。
 */
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  ParamProfile,
  ParamProfileCloneInput,
  ParamProfileInput,
  ParamProfileScope,
} from '@/domain/models/paramProfile'
import {
  cloneProfile,
  createProfile,
  deleteProfile,
  getProfile,
  listProfiles,
  updateProfile,
} from '@/infrastructure/api/param-profile-api'

const PARAM_PROFILE_QUERY_ROOT = ['algorithm-config', 'param-profiles'] as const

export const paramProfileQueryKeys = {
  list: (algorithmType: string | null, scope: ParamProfileScope | null) =>
    [
      ...PARAM_PROFILE_QUERY_ROOT,
      'list',
      algorithmType ?? 'all',
      scope ?? 'all',
    ] as const,
  detail: (profileId: number | null) =>
    [...PARAM_PROFILE_QUERY_ROOT, 'detail', profileId] as const,
}

export interface ParamProfileListResult {
  profiles: ParamProfile[]
  isLoading: boolean
  isError: boolean
}

/**
 * 列表（algorithmType = null → 全部；scope = null → 全部作用域）
 *
 * 作用域是策略的语义分界：api 策略的字段/映射面向 API 输出，device 策略面向
 * 设备输出，两者的来源词表不同，必须由各自入口过滤后编辑（INT-2267）。
 */
export function useParamProfileList(
  algorithmType: string | null,
  scope: ParamProfileScope | null,
  enabled: boolean
): ParamProfileListResult {
  const query = useQuery({
    queryKey: paramProfileQueryKeys.list(algorithmType, scope),
    queryFn: () => listProfiles(algorithmType ?? undefined, scope ?? undefined),
    enabled,
    staleTime: 0,
    retry: false,
  })
  return {
    profiles: query.data?.profiles ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
  }
}

/** 编辑前取详情（列表不带 params / mappings） */
export function useParamProfileDetail(profileId: number | null, enabled: boolean) {
  const query = useQuery({
    queryKey: paramProfileQueryKeys.detail(profileId),
    queryFn: () => getProfile(profileId as number),
    enabled: enabled && profileId != null,
    staleTime: 0,
    retry: false,
  })
  return {
    profile: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
  }
}

export interface ParamProfileCounts {
  paramCount: number
  mappingCount: number
}

/**
 * 列表行的「字段 / 映射」计数。
 *
 * 列表接口（`GET /algorithm/param-profiles`）只返回策略基础字段，没有
 * `params` / `mappings`，也没有计数列，直接读列表项会恒为 0（INT-2358）。
 * 这里按策略逐条取详情计数：当前真实库策略量很小（个位数），且详情查询与
 * 编辑弹窗共用 `detail(id)` 缓存键，编辑过一次就不会重复请求。
 * 未取到（加载中 / 失败）的策略不出现在结果里，调用方按「未知」展示，
 * 不把未知渲染成 0。
 */
export function useParamProfileCounts(
  profiles: ParamProfile[],
  enabled: boolean
): Record<number, ParamProfileCounts> {
  const detailQueries = useQueries({
    queries: profiles.map((profile) => ({
      queryKey: paramProfileQueryKeys.detail(profile.id),
      queryFn: () => getProfile(profile.id),
      enabled,
      // 列表计数不要求强实时：短时间内重复开关弹窗不重复打接口
      staleTime: 30_000,
      retry: false,
    })),
  })
  const counts: Record<number, ParamProfileCounts> = {}
  profiles.forEach((profile, index) => {
    const detail = detailQueries[index]?.data
    if (!detail) return
    counts[profile.id] = {
      paramCount: detail.params.length,
      mappingCount: detail.mappings.length,
    }
  })
  return counts
}

/** 保存（id 为空 → 新建；否则整份更新）、克隆、删除 */
export function useParamProfileMutations() {
  const queryClient = useQueryClient()

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: PARAM_PROFILE_QUERY_ROOT })
    void queryClient.invalidateQueries({
      queryKey: ['test-execution', 'api-dialog', 'param-profiles'],
    })
  }

  const save = useMutation({
    mutationFn: ({ profileId, input }: { profileId: number | null; input: ParamProfileInput }) =>
      profileId == null ? createProfile(input) : updateProfile(profileId, input),
    onSuccess: invalidate,
  })

  const clone = useMutation({
    mutationFn: ({ profileId, input }: { profileId: number; input: ParamProfileCloneInput }) =>
      cloneProfile(profileId, input),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (profileId: number) => deleteProfile(profileId),
    onSuccess: invalidate,
  })

  return { save, clone, remove }
}

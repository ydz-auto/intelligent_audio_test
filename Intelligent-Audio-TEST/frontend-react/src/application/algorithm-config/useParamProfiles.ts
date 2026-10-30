/**
 * 参数策略管理编排（application 层；T4.3）。
 *
 * 列表 / 详情 / 保存 / 克隆 / 删除都走 infrastructure/api/param-profile-api；
 * 本层只做查询键统一与失效，不在界面层拼供数逻辑。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  ParamProfile,
  ParamProfileCloneInput,
  ParamProfileInput,
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
  list: (algorithmType: string | null) =>
    [...PARAM_PROFILE_QUERY_ROOT, 'list', algorithmType ?? 'all'] as const,
  detail: (profileId: number | null) =>
    [...PARAM_PROFILE_QUERY_ROOT, 'detail', profileId] as const,
}

export interface ParamProfileListResult {
  profiles: ParamProfile[]
  isLoading: boolean
  isError: boolean
}

/** 列表（algorithmType = null → 全部） */
export function useParamProfileList(
  algorithmType: string | null,
  enabled: boolean
): ParamProfileListResult {
  const query = useQuery({
    queryKey: paramProfileQueryKeys.list(algorithmType),
    queryFn: () => listProfiles(algorithmType ?? undefined),
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

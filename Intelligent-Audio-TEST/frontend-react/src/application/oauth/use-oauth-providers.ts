/**
 * OAuth 提供方 query/mutations（application 层，INT-729 接线后）：
 * 列表 GET /auth/oauth-providers；CRUD + 自动发现三件套；保存后 invalidate
 * （对齐 newAPI custom-oauth 缓存失效模式）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { OAuthProvider } from '@/domain/models/oauth-provider'
import {
  createProvider,
  deleteProvider,
  discoverEndpoints,
  getOAuthProviders,
  OAUTH_PROVIDERS_QUERY_KEY,
  updateProvider,
} from '@/infrastructure/api/oauthProviderApi'

export function useOAuthProvidersQuery() {
  return useQuery({
    queryKey: [...OAUTH_PROVIDERS_QUERY_KEY],
    queryFn: getOAuthProviders,
    staleTime: 30_000,
  })
}

export function useOAuthProviderMutations() {
  const queryClient = useQueryClient()

  const invalidate = () =>
    void queryClient.invalidateQueries({ queryKey: OAUTH_PROVIDERS_QUERY_KEY })

  const createProviderMutation = useMutation({
    mutationFn: createProvider,
    onSuccess: () => {
      toast.success('提供方已创建')
      invalidate()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  const updateProviderMutation = useMutation({
    mutationFn: (args: { providerId: string; patch: Partial<OAuthProvider> }) =>
      updateProvider(args.providerId, args.patch),
    onSuccess: () => {
      toast.success('提供方已更新')
      invalidate()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  const deleteProviderMutation = useMutation({
    mutationFn: (providerId: string) => deleteProvider(providerId),
    onSuccess: () => {
      toast.success('提供方已删除')
      invalidate()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  return {
    createProvider: createProviderMutation,
    updateProvider: updateProviderMutation,
    deleteProvider: deleteProviderMutation,
    discoverEndpoints,
  }
}

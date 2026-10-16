/**
 * OAuth 提供方 query/mutations（application 层，INT-347 §4.2 母版 B）：
 * 列表 GET /oauth-providers；CRUD + 自动发现三件套；保存后 invalidate（对齐
 * newAPI custom-oauth 缓存失效模式）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { OAuthProvider } from '@/domain/models/oauth-provider'
import {
  createMockProvider,
  deleteMockProvider,
  discoverEndpoints,
  getOAuthProviders,
  OAUTH_PROVIDERS_QUERY_KEY,
  updateMockProvider,
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

  const createProvider = useMutation({
    mutationFn: createMockProvider,
    onSuccess: () => {
      toast.success('提供方已创建')
      invalidate()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  const updateProvider = useMutation({
    mutationFn: (args: { providerId: string; patch: Partial<OAuthProvider> }) =>
      updateMockProvider(args.providerId, args.patch),
    onSuccess: () => {
      toast.success('提供方已更新')
      invalidate()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  const deleteProvider = useMutation({
    mutationFn: deleteMockProvider,
    onSuccess: () => {
      toast.success('提供方已删除')
      invalidate()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  return { createProvider, updateProvider, deleteProvider, discoverEndpoints }
}

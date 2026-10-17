/**
 * OAuth 绑定用例 hooks（application 层，13_个人中心.md §3.5.2/§7）：
 * 提供方列表（公开）+ 绑定列表 + 绑定（携票）/解绑 mutations，成功后 invalidate。
 * 绑定中/解绑中全组禁用（bindingsLocked 语义，§3.5.2），避免并发。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'
import { toast } from 'sonner'

import type { OAuthProvider } from '@/domain/models/auth'
import type { OAuthBinding } from '@/domain/models/profile'
import { authApi } from '@/infrastructure/api/authApi'
import {
  completeOAuthBinding,
  listOAuthBindings,
  OAUTH_BINDINGS_QUERY_KEY,
  unbindOAuthBinding,
} from '@/infrastructure/api/profileApi'

export function useOAuthBindings() {
  const queryClient = useQueryClient()

  const providersQuery = useQuery({
    queryKey: ['auth', 'oauth', 'providers'],
    queryFn: () => authApi.listPublicOAuthProviders(),
    staleTime: 30_000,
  })
  const bindingsQuery = useQuery({
    queryKey: [...OAUTH_BINDINGS_QUERY_KEY],
    queryFn: listOAuthBindings,
    staleTime: 30_000,
  })

  const invalidateBindings = () =>
    void queryClient.invalidateQueries({ queryKey: ['auth', 'oauth'] })

  const bindMutation = useMutation({
    mutationFn: completeOAuthBinding,
    onSuccess: () => {
      toast.success('绑定成功')
      invalidateBindings()
    },
    onError: (error) =>
      toast.error(`绑定失败：${error instanceof Error ? error.message : '未知原因'}`),
  })

  const unbindMutation = useMutation({
    mutationFn: unbindOAuthBinding,
    onSuccess: () => {
      toast.success('解绑成功')
      invalidateBindings()
    },
    onError: (error) =>
      toast.error(`解绑失败：${error instanceof Error ? error.message : '未知原因'}`),
  })

  /** 绑定中/解绑中全组禁用（§3.5.2 bindingsLocked 语义） */
  const bindingsLocked = bindMutation.isPending || unbindMutation.isPending

  /** 提供方 × 绑定态合并行（提供方启用项全量渲染；绑定信息叠加到对应行） */
  const rows = useMemo(() => {
    const providers = providersQuery.data ?? []
    const bindingMap = new Map(
      (bindingsQuery.data ?? []).map((binding: OAuthBinding) => [
        binding.providerId,
        binding,
      ])
    )
    return providers.map((provider: OAuthProvider) => ({
      provider,
      binding: bindingMap.get(provider.id),
    }))
  }, [providersQuery.data, bindingsQuery.data])

  return {
    providers: providersQuery.data ?? [],
    bindings: bindingsQuery.data ?? [],
    rows,
    isLoading:
      providersQuery.isLoading ||
      bindingsQuery.isLoading ||
      providersQuery.isPending ||
      bindingsQuery.isPending,
    bindingsLocked,
    bind: bindMutation.mutate,
    unbind: unbindMutation.mutate,
  }
}

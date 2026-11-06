/**
 * Access Token query + mutation（application 层，INT-1153）。
 * GET /auth/access-tokens 列表（token_hint 掩码）+ POST/PATCH/DELETE 变更，
 * 变更后 invalidate 列表缓存联动 /profile 与入口页面两处展示。
 * 创建成功返回的明文 token 由页面层持有（明文只显示一次，不落 Query 缓存）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type {
  AccessToken,
  AccessTokenStatus,
} from '@/domain/models/access-token'
import type { AccessTokenExpiryValue } from '@/infrastructure/dto/access-token.dto'
import {
  createAccessToken,
  deleteAccessToken,
  listAccessTokens,
  updateAccessToken,
} from '@/infrastructure/api/accessTokenApi'

export const ACCESS_TOKENS_QUERY_KEY = ['profile', 'access-tokens'] as const

export function useAccessTokensQuery() {
  return useQuery({
    queryKey: [...ACCESS_TOKENS_QUERY_KEY],
    queryFn: listAccessTokens,
    staleTime: 30_000,
    retry: false,
  })
}

export function useAccessTokenMutations() {
  const queryClient = useQueryClient()

  const invalidate = () =>
    void queryClient.invalidateQueries({ queryKey: ACCESS_TOKENS_QUERY_KEY })

  const create = useMutation({
    mutationFn: (input: {
      name: string
      scopes: string[]
      expiresAt: AccessTokenExpiryValue
    }) => createAccessToken(input),
    onSuccess: () => invalidate(),
    onError: (error: unknown) => {
      toast.error(
        error instanceof Error && error.message ? error.message : '创建 Access Token 失败'
      )
    },
  })

  const update = useMutation({
    mutationFn: (args: {
      id: string
      input: {
        name?: string
        scopes?: string[]
        expiresAt?: AccessTokenExpiryValue
        status?: AccessTokenStatus
      }
    }) => updateAccessToken(args.id, args.input),
    onSuccess: () => {
      toast.success('已保存')
      invalidate()
    },
    onError: (error: unknown) => {
      toast.error(
        error instanceof Error && error.message ? error.message : '保存失败'
      )
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteAccessToken(id),
    onSuccess: () => {
      toast.success('Access Token 已删除')
      invalidate()
    },
    onError: (error: unknown) => {
      toast.error(
        error instanceof Error && error.message ? error.message : '删除失败'
      )
    },
  })

  return { create, update, remove, invalidate }
}

export type { AccessToken }

/**
 * 公开 OAuth 提供方 query（application 层，12_登录与错误页.md §3.5/§9）：
 * GET /auth/oauth/providers 公开端点；提供方由运维配置，staleTime 长缓存。
 */
import { useQuery } from '@tanstack/react-query'

import type { OAuthProvider } from '@/domain/models/auth'
import { authApi } from '@/infrastructure/api/authApi'

export const PUBLIC_OAUTH_PROVIDERS_QUERY_KEY = ['auth', 'oauth', 'providers']

export function usePublicOAuthProviders() {
  return useQuery<OAuthProvider[]>({
    queryKey: PUBLIC_OAUTH_PROVIDERS_QUERY_KEY,
    queryFn: () => authApi.listPublicOAuthProviders(),
    staleTime: 5 * 60_000,
  })
}

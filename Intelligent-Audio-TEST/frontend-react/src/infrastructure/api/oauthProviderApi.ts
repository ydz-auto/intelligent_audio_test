/**
 * 自定义 OAuth 提供方 API 桩（infrastructure 层，红线④：mock 常量）。
 * 契约对位 newAPI custom-oauth（表/对话框/自动发现三件套）；
 * 本平台后端能力：无 OAuth 提供方 CRUD 接口（主库 OAuthProviderManagement.vue 前端内联）。
 * TODO(API 接线): 提供方 CRUD + 自动发现端点需后端落接口（如无能力开【FEAT】卡），
 * 形态建议：GET/POST/PUT/DELETE /api/v1/auth/oauth-providers + POST /discover（Issuer URL → 三端点）。
 */
import type { OAuthProvider } from '@/domain/models/oauth-provider'
import {
  MOCK_OAUTH_PROVIDERS,
  mockDiscoverEndpoints,
} from '@/infrastructure/mock/oauth-mock'

export const OAUTH_PROVIDERS_QUERY_KEY = ['auth', 'oauth-providers'] as const

export async function getOAuthProviders(): Promise<OAuthProvider[]> {
  return MOCK_OAUTH_PROVIDERS
}

export async function discoverEndpoints(issuerUrl: string): Promise<{
  authorizationEndpoint: string
  tokenEndpoint: string
  userinfoEndpoint: string
} | null> {
  return mockDiscoverEndpoints(issuerUrl)
}

export async function createMockProvider(
  input: Omit<OAuthProvider, 'id' | 'createdAt'>
): Promise<OAuthProvider> {
  const provider: OAuthProvider = {
    ...input,
    id: `provider-${Date.now()}`,
    createdAt: new Date().toISOString(),
  }
  MOCK_OAUTH_PROVIDERS.push(provider)
  return provider
}

export async function updateMockProvider(
  providerId: string,
  patch: Partial<OAuthProvider>
): Promise<OAuthProvider> {
  const index = MOCK_OAUTH_PROVIDERS.findIndex((p) => p.id === providerId)
  if (index === -1) throw new Error(`提供方不存在：${providerId}`)
  MOCK_OAUTH_PROVIDERS[index] = { ...MOCK_OAUTH_PROVIDERS[index], ...patch }
  return MOCK_OAUTH_PROVIDERS[index]
}

export async function deleteMockProvider(providerId: string): Promise<void> {
  const index = MOCK_OAUTH_PROVIDERS.findIndex((p) => p.id === providerId)
  if (index !== -1) MOCK_OAUTH_PROVIDERS.splice(index, 1)
}

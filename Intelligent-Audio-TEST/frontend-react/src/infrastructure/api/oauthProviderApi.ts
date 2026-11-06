/**
 * 自定义 OAuth 提供方 API（infrastructure 层，INT-729 接线）。
 * 契约对照 api_gateway/routes/oauth_bp.py + oauth_provider_service 实测：
 * GET /auth/oauth-providers（auth:manage_provider，{providers:[to_admin_dict]}——
 * client_secret 掩去为 has_client_secret）；POST/PUT/DELETE /auth/oauth-providers[/{id}]
 * （create 全字段、update 键缺省=不修改/空 secret=保留原值、delete）；
 * POST /auth/oauth/admin/discovery（{issuer_url} → {well_known_url, discovery}）。
 * snake_case → camelCase 收敛于 iam-adapter；interfaces 只消费 OAuthProvider 域对象。
 */
import { apiClient } from './client'
import type { OAuthProvider, OAuthFieldMapping } from '@/domain/models/oauth-provider'
import { toOAuthProvider, toOAuthProviderCreatePayload } from '@/infrastructure/adapters/dto/iam-adapter'
import type { OAuthDiscoveryDto, OAuthProvidersPageDto } from '@/infrastructure/dto/iam.dto'

export const OAUTH_PROVIDERS_QUERY_KEY = ['auth', 'oauth-providers'] as const

export async function getOAuthProviders(): Promise<OAuthProvider[]> {
  const dto = await apiClient.get<OAuthProvidersPageDto>('/auth/oauth-providers')
  return (dto.providers ?? []).map(toOAuthProvider)
}

export async function discoverEndpoints(issuerUrl: string): Promise<{
  authorizationEndpoint: string
  tokenEndpoint: string
  userinfoEndpoint: string
} | null> {
  const dto = await apiClient.post<OAuthDiscoveryDto>(
    '/auth/oauth/admin/discovery',
    { issuer_url: issuerUrl }
  )
  const discovery = dto?.discovery
  if (!discovery) return null
  return {
    authorizationEndpoint: discovery.authorization_endpoint ?? '',
    tokenEndpoint: discovery.token_endpoint ?? '',
    userinfoEndpoint: discovery.userinfo_endpoint ?? '',
  }
}

export async function createProvider(
  input: Omit<OAuthProvider, 'id' | 'createdAt'> & { clientSecret?: string }
): Promise<void> {
  await apiClient.post('/auth/oauth-providers', toOAuthProviderCreatePayload(input))
}

const DIRECT_PATCH_FIELDS: Array<[string, keyof OAuthProvider]> = [
  ['name', 'name'],
  ['slug', 'slug'],
  ['icon', 'icon'],
  ['client_id', 'clientId'],
  ['client_secret', 'clientSecret'],
  ['authorize_url', 'authorizationEndpoint'],
  ['token_url', 'tokenEndpoint'],
  ['userinfo_url', 'userinfoEndpoint'],
  ['scopes', 'scopes'],
]

const MAPPING_PATCH_FIELDS: Array<[string, keyof OAuthFieldMapping]> = [
  ['user_id_field', 'userIdentifier'],
  ['username_field', 'userName'],
  ['display_name_field', 'displayName'],
  ['email_field', 'email'],
]

export async function updateProvider(
  providerId: string,
  patch: Partial<OAuthProvider> & { clientSecret?: string }
): Promise<void> {
  const body: Record<string, string | boolean> = {}
  for (const [backendKey, domainField] of DIRECT_PATCH_FIELDS) {
    const value = patch[domainField]
    if (typeof value === 'string' && value !== '') body[backendKey] = value
  }
  if (patch.fieldMapping) {
    for (const [backendKey, field] of MAPPING_PATCH_FIELDS) {
      const value = patch.fieldMapping[field]
      if (value && value !== '') body[backendKey] = value
    }
  }
  if (patch.status !== undefined) body.enabled = patch.status === 'enabled'
  await apiClient.put(`/auth/oauth-providers/${providerId}`, body)
}

export async function deleteProvider(providerId: string): Promise<void> {
  await apiClient.delete(`/auth/oauth-providers/${providerId}`)
}

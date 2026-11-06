/**
 * 自定义 OAuth 提供方 mock 数据源（infrastructure 层，红线④：mock 常量）。
 * 字段形态对照 OAuthProviderManagement.vue + newAPI custom-oauth 三件套
 * （自动发现 Issuer URL 回填三端点 + 四字段映射）。
 */
import type { OAuthProvider } from '@/domain/models/oauth-provider'

export const MOCK_OAUTH_PROVIDERS: OAuthProvider[] = [
  {
    id: 'provider-github',
    name: 'GitHub',
    slug: 'github',
    icon: 'github',
    status: 'enabled',
    clientId: 'Iv1.8b7e3c9f2a6d4e10',
    clientSecret: '••••••••••••••••',
    authorizationEndpoint: 'https://github.com/login/oauth/authorize',
    tokenEndpoint: 'https://github.com/login/oauth/access_token',
    userinfoEndpoint: 'https://api.github.com/user',
    scopes: 'read:user user:email',
    fieldMapping: {
      userIdentifier: 'sub',
      userName: 'preferred_username',
      displayName: 'name',
      email: 'email',
    },
    createdAt: '2026-02-18T04:00:00Z',
  },
  {
    id: 'provider-gitlab',
    name: 'GitLab',
    slug: 'gitlab',
    icon: 'gitlab',
    status: 'enabled',
    clientId: 'glpat-2f9c8d7e6b5a4c3d',
    clientSecret: '••••••••••••••••',
    authorizationEndpoint: 'https://gitlab.com/oauth/authorize',
    tokenEndpoint: 'https://gitlab.com/oauth/token',
    userinfoEndpoint: 'https://gitlab.com/api/v4/user',
    scopes: 'read_user',
    fieldMapping: {
      userIdentifier: 'sub',
      userName: 'preferred_username',
      displayName: 'name',
      email: 'email',
    },
    createdAt: '2026-03-01T09:30:00Z',
  },
  {
    id: 'provider-corp',
    name: '企业微信',
    slug: 'wecom',
    icon: 'wecom',
    status: 'disabled',
    clientId: 'ww8e6d4c2b1a9f0e',
    clientSecret: '••••••••••••••••',
    authorizationEndpoint: 'https://open.weixin.qq.com/connect/oauth2/authorize',
    tokenEndpoint: 'https://qyapi.weixin.qq.com/cgi-bin/gettoken',
    userinfoEndpoint: 'https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo',
    scopes: 'snsapi_base',
    fieldMapping: {
      userIdentifier: 'userid',
      userName: 'name',
      displayName: 'name',
      email: 'email',
    },
    createdAt: '2026-04-08T11:45:00Z',
  },
]

/** mock：自动发现端点（Issuer URL → 三端点回填；照 newAPI custom-oauth 三件套） */
export function mockDiscoverEndpoints(
  issuerUrl: string
): {
  authorizationEndpoint: string
  tokenEndpoint: string
  userinfoEndpoint: string
} | null {
  const trimmed = issuerUrl.trim()
  if (!trimmed) return null
  return {
    authorizationEndpoint: `${trimmed}/protocol/openid-connect/auth`,
    tokenEndpoint: `${trimmed}/protocol/openid-connect/token`,
    userinfoEndpoint: `${trimmed}/protocol/openid-connect/userinfo`,
  }
}

export async function fetchMockOAuthProviders(): Promise<OAuthProvider[]> {
  return MOCK_OAUTH_PROVIDERS
}

/**
 * 自定义 OAuth 提供方领域模型（domain 层）。
 * 字段对照 OAuthProviderManagement.vue（现状）+ newAPI custom-oauth 三件套：
 * 自动发现（Issuer URL → 回填授权/Token/用户信息端点）+ 字段映射四段。
 */

export type OAuthProviderStatus = 'enabled' | 'disabled'

export type OAuthFieldMapping = {
  /** 用户标识字段（默认 sub） */
  userIdentifier: string
  /** 用户名字段（默认 preferred_username） */
  userName: string
  /** 显示名字段（默认 name） */
  displayName: string
  /** 邮箱字段（默认 email） */
  email: string
}

export type OAuthProvider = {
  id: string
  name: string
  slug: string
  icon?: string
  status: OAuthProviderStatus
  clientId: string
  /** 编辑态留空保留原值；列表不展示 */
  clientSecret?: string
  authorizationEndpoint: string
  tokenEndpoint: string
  userinfoEndpoint: string
  /** 请求范围（空格分隔字符串形态，照 newAPI） */
  scopes: string
  /** 用户标识/用户名/显示名/邮箱字段映射（默认 sub/preferred_username/name/email） */
  fieldMapping: OAuthFieldMapping
  createdAt: string
}

export const OAUTH_PROVIDER_STATUS_META: Record<
  OAuthProviderStatus,
  { label: string }
> = {
  enabled: { label: '启用' },
  disabled: { label: '停用' },
}

/** 回调地址模板（§6 说明 Alert code 样式 + CopyButton） */
export const OAUTH_CALLBACK_TEMPLATE = 'https://api.example.com/auth/callback/{slug}'

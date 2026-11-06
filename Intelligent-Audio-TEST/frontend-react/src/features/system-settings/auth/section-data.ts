/**
 * 认证设置域分区常量（interfaces 层，INT-347 §3.2/§6）：
 * 认证方式（随管理员口径）/ OAuth 提供方（auth:manage_provider 独立分区门槛）。
 */
export const AUTH_SECTIONS = [
  { id: 'methods', title: '认证方式' },
  {
    id: 'oauth-providers',
    title: 'OAuth 提供方',
    requiredPermission: 'auth:manage_provider',
  },
] as const

export type AuthSectionId = (typeof AUTH_SECTIONS)[number]['id']

export const AUTH_SECTION_IDS = AUTH_SECTIONS.map((s) => s.id) as [
  AuthSectionId,
  ...AuthSectionId[],
]

export const AUTH_DEFAULT_SECTION = 'methods'

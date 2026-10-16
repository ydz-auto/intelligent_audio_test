/**
 * 系统设置选项领域模型（domain 层）。
 * 形态对照 newAPI `/api/option/` KV 通道（get_global_option 布尔/数字/字符串/数组，
 * 前端按默认值类型安全解析）；本平台选项接口待建（实施前置），mock 与接线形态同构。
 */

export type SystemOptionValue = string | number | boolean | string[]

/** 系统选项 KV 记录：键 = `域.分区.字段`，值类型与默认值一致 */
export type SystemOptions = Record<string, SystemOptionValue>

/** 布尔解析：`value==='true'||'1'`（对齐 newAPI use-system-options 实测） */
export function parseBoolean(
  value: SystemOptionValue | undefined,
  fallback: boolean
): boolean {
  if (typeof value === 'boolean') return value
  if (typeof value === 'string') return value === 'true' || value === '1'
  if (typeof value === 'number') return value !== 0
  return fallback
}

/** 数字解析：`Number(trim)` 失败回退默认（对齐 newAPI 实测） */
export function parseNumber(
  value: SystemOptionValue | undefined,
  fallback: number
): number {
  if (typeof value === 'number') return value
  if (typeof value === 'string') {
    const parsed = Number(value.trim())
    return Number.isNaN(parsed) ? fallback : parsed
  }
  return fallback
}

export function parseString(
  value: SystemOptionValue | undefined,
  fallback: string
): string {
  return typeof value === 'string' ? value : fallback
}

/** 数组解析：JSON.parse + 元素类型校验，失败回退默认（对齐 newAPI 实测） */
export function parseStringArray(
  value: SystemOptionValue | undefined,
  fallback: string[]
): string[] {
  if (Array.isArray(value)) return value.filter((v) => typeof v === 'string')
  if (typeof value === 'string') {
    try {
      const parsed: unknown = JSON.parse(value)
      if (Array.isArray(parsed)) {
        return parsed.filter((v): v is string => typeof v === 'string')
      }
    } catch {
      // 非法 JSON 回退默认
    }
  }
  return fallback
}

/**
 * 系统选项默认值（可视稿基线；实施前置选项接口落定后按域拆分 REST，仅替换
 * infrastructure 层读写，interfaces/application 不感知）。
 */
export const SYSTEM_OPTION_DEFAULTS: SystemOptions = {
  // 站点设置 · 站点信息
  'site.name': '智能语音测试平台',
  'site.logo': '',
  'site.footer': '',
  // 站点设置 · 站点公告
  'site.notice': '',
  // 站点设置 · 导航模块
  'site.navigation.show_breadcrumb': true,
  'site.navigation.show_algorithm_switcher': true,
  // 认证设置 · 认证方式
  'auth.password_login': true,
  'auth.registration': true,
  'auth.email_verification': false,
  // 安全设置 · 访问控制
  'security.rate_limit': true,
  // 运维设置 · 日志维护
  'operations.log_retention_days': 30,
}

export type SiteInfoSettings = {
  name: string
  logo: string
  footer: string
}

export type SiteNoticeSettings = {
  notice: string
}

export type SiteNavigationSettings = {
  showBreadcrumb: boolean
  showAlgorithmSwitcher: boolean
}

export type AuthMethodSettings = {
  passwordLogin: boolean
  registration: boolean
  emailVerification: boolean
}

export type AccessControlSettings = {
  rateLimit: boolean
}

export type LogMaintenanceSettings = {
  retentionDays: number
}

/** 站点信息域解析（KV → 类型化设置） */
export function resolveSiteInfoSettings(raw?: SystemOptions): SiteInfoSettings {
  return {
    name: parseString(raw?.['site.name'], SYSTEM_OPTION_DEFAULTS['site.name'] as string),
    logo: parseString(raw?.['site.logo'], SYSTEM_OPTION_DEFAULTS['site.logo'] as string),
    footer: parseString(raw?.['site.footer'], SYSTEM_OPTION_DEFAULTS['site.footer'] as string),
  }
}

export function resolveSiteNoticeSettings(raw?: SystemOptions): SiteNoticeSettings {
  return {
    notice: parseString(raw?.['site.notice'], SYSTEM_OPTION_DEFAULTS['site.notice'] as string),
  }
}

export function resolveSiteNavigationSettings(
  raw?: SystemOptions
): SiteNavigationSettings {
  return {
    showBreadcrumb: parseBoolean(
      raw?.['site.navigation.show_breadcrumb'],
      SYSTEM_OPTION_DEFAULTS['site.navigation.show_breadcrumb'] as boolean
    ),
    showAlgorithmSwitcher: parseBoolean(
      raw?.['site.navigation.show_algorithm_switcher'],
      SYSTEM_OPTION_DEFAULTS['site.navigation.show_algorithm_switcher'] as boolean
    ),
  }
}

export function resolveAuthMethodSettings(raw?: SystemOptions): AuthMethodSettings {
  return {
    passwordLogin: parseBoolean(
      raw?.['auth.password_login'],
      SYSTEM_OPTION_DEFAULTS['auth.password_login'] as boolean
    ),
    registration: parseBoolean(
      raw?.['auth.registration'],
      SYSTEM_OPTION_DEFAULTS['auth.registration'] as boolean
    ),
    emailVerification: parseBoolean(
      raw?.['auth.email_verification'],
      SYSTEM_OPTION_DEFAULTS['auth.email_verification'] as boolean
    ),
  }
}

export function resolveAccessControlSettings(
  raw?: SystemOptions
): AccessControlSettings {
  return {
    rateLimit: parseBoolean(
      raw?.['security.rate_limit'],
      SYSTEM_OPTION_DEFAULTS['security.rate_limit'] as boolean
    ),
  }
}

export function resolveLogMaintenanceSettings(
  raw?: SystemOptions
): LogMaintenanceSettings {
  return {
    retentionDays: parseNumber(
      raw?.['operations.log_retention_days'],
      SYSTEM_OPTION_DEFAULTS['operations.log_retention_days'] as number
    ),
  }
}

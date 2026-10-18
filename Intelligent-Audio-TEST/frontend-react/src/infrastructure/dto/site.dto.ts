/**
 * 站点配置 DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换层）。
 * 对照主库 home/site 配置端点契约（接线壳 INT-607；端点未落，字段形态按
 * 站点信息 KV 惯例预置：system_name / version / logo / support_email）。
 * snake→camel 转换收敛在本文件，application/domain 只见 camelCase。
 */
import type { SiteConfig } from '@/domain/models/site'

/** 后端 site 配置响应（snake_case wire 契约；字段缺省回退默认） */
export interface SiteConfigDto {
  system_name?: string | null
  version?: string | null
  logo?: string | null
  support_email?: string | null
}

/** snake_case → camelCase Domain（缺字段回落 DEFAULT_SITE_CONFIG 对应值） */
export function toSiteConfig(raw: SiteConfigDto): SiteConfig {
  return {
    systemName: raw.system_name || '智能语音测试平台',
    version: raw.version || '演示版',
    logo: raw.logo || '',
    supportEmail: raw.support_email || '',
  }
}

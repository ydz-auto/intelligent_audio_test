/**
 * 设置工作区六域注册表（interfaces 层，INT-347 §3.2 定稿）：
 * 站点设置/用户与权限/认证设置/外观与主题/安全设置/运维设置。
 * 侧栏树（layout/config/system-settings.config.ts）与路由守卫共用本表，
 * 域级门槛 = 域可见性权限（不满足整组隐藏），分区级门槛见各 section-data。
 */
import {
  Palette,
  Settings,
  Shield,
  ShieldAlert,
  Users,
  Wrench,
  type LucideIcon,
} from 'lucide-react'

import { APPEARANCE_DEFAULT_SECTION, APPEARANCE_SECTION_IDS, APPEARANCE_SECTIONS } from './appearance/section-data'
import { AUTH_DEFAULT_SECTION, AUTH_SECTION_IDS, AUTH_SECTIONS } from './auth/section-data'
import { IAM_DEFAULT_SECTION, IAM_SECTION_IDS, IAM_SECTIONS } from './iam/section-data'
import { OPERATIONS_DEFAULT_SECTION, OPERATIONS_SECTION_IDS, OPERATIONS_SECTIONS } from './operations/section-data'
import { SECURITY_DEFAULT_SECTION, SECURITY_SECTION_IDS, SECURITY_SECTIONS } from './security/section-data'
import { SITE_DEFAULT_SECTION, SITE_SECTION_IDS, SITE_SECTIONS } from './site/section-data'

export type SettingsDomainSection = {
  id: string
  title: string
  requiredPermission?: string
  requiredPermissions?: string[]
}

export type SettingsDomain = {
  id: string
  title: string
  icon: LucideIcon
  /** 域可见性门槛（不满足整组隐藏，对齐 newAPI requiredRole「隐藏而非置灰」） */
  requiredPermission?: string
  requiredPermissions?: string[]
  defaultSection: string
  sections: readonly SettingsDomainSection[]
}

/** 六域全量（INT-417 收敛后设置树） */
export const SETTINGS_DOMAINS: SettingsDomain[] = [
  {
    id: 'site',
    title: '站点设置',
    icon: Settings,
    // 站点设置无独立权限码，随 user:read 同级口径（admin 判定）
    requiredPermission: 'user:read',
    defaultSection: SITE_DEFAULT_SECTION,
    sections: SITE_SECTIONS,
  },
  {
    id: 'iam',
    title: '用户与权限',
    icon: Users,
    requiredPermission: 'user:read',
    defaultSection: IAM_DEFAULT_SECTION,
    sections: IAM_SECTIONS,
  },
  {
    id: 'auth',
    title: '认证设置',
    icon: Shield,
    // 认证方式随管理员口径、OAuth 提供方随 auth:manage_provider
    requiredPermissions: ['auth:manage_provider', 'user:read'],
    defaultSection: AUTH_DEFAULT_SECTION,
    sections: AUTH_SECTIONS,
  },
  {
    id: 'appearance',
    title: '外观与主题',
    icon: Palette,
    // 全员登录用户（个人偏好，无资源写权限，不进管理员守卫范围）
    defaultSection: APPEARANCE_DEFAULT_SECTION,
    sections: APPEARANCE_SECTIONS,
  },
  {
    id: 'security',
    title: '安全设置',
    icon: ShieldAlert,
    requiredPermission: 'user:read',
    defaultSection: SECURITY_DEFAULT_SECTION,
    sections: SECURITY_SECTIONS,
  },
  {
    id: 'operations',
    title: '运维设置',
    icon: Wrench,
    requiredPermission: 'log:manage',
    defaultSection: OPERATIONS_DEFAULT_SECTION,
    sections: OPERATIONS_SECTIONS,
  },
]

/** 域 id 白名单（路由校验用） */
export const SETTINGS_DOMAIN_IDS = SETTINGS_DOMAINS.map((domain) => domain.id)

/** 按域 id 取定义 */
export function getSettingsDomain(domainId: string): SettingsDomain | undefined {
  return SETTINGS_DOMAINS.find((domain) => domain.id === domainId)
}

/** 工作区默认落点（首个域默认分区） */
export const SYSTEM_SETTINGS_DEFAULT_PATH = `/system-settings/${SETTINGS_DOMAINS[0].id}/${SETTINGS_DOMAINS[0].defaultSection}`

/** 域 → 默认分区路径（/system-settings/<域> 重定向目标） */
export function getDomainDefaultPath(domainId: string): string {
  const domain = getSettingsDomain(domainId)
  return domain ? `/system-settings/${domain.id}/${domain.defaultSection}` : SYSTEM_SETTINGS_DEFAULT_PATH
}

/** 域 → 图标（侧栏树构建用；LayoutGrid 为「系统管理」组标签占位，未直接使用） */
export const SETTINGS_DOMAIN_ICONS: Record<string, LucideIcon> = {
  site: Settings,
  iam: Users,
  auth: Shield,
  appearance: Palette,
  security: ShieldAlert,
  operations: Wrench,
}

/** 供类型消费：六域 section 白名单展开 */
export const SETTINGS_SECTION_IDS = {
  site: SITE_SECTION_IDS,
  iam: IAM_SECTION_IDS,
  auth: AUTH_SECTION_IDS,
  appearance: APPEARANCE_SECTION_IDS,
  security: SECURITY_SECTION_IDS,
  operations: OPERATIONS_SECTION_IDS,
} as const

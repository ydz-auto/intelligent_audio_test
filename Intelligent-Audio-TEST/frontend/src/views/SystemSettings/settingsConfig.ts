/**
 * 系统设置工作区 —— 六域设置树配置（照总表 §2.5 与 React features/system-settings/domains.ts）
 *
 * - 域级门槛 = 域可见性权限（string 单码 / string[] 任一）
 * - 分区级门槛：undefined 继承域门槛；显式权限则按分区额外判定
 * - appearance 域无域门槛（登录即可，仅直接 URL 可达，总表 §2.5）
 */
export interface SettingsSection {
  /** 相对路径（/system-settings/<path>），如 'site/info' */
  path: string
  label: string
  /** 分区级权限门槛（undefined = 继承域门槛） */
  permission?: string
}

export interface SettingsDomain {
  id: string
  title: string
  icon: string
  permission?: string | string[]
  defaultSection: string
  sections: SettingsSection[]
}

export const SYSTEM_SETTINGS_PERMISSIONS = [
  'user:read',
  'role:read',
  'auth:manage_provider',
  'log:manage',
] as const

export const settingsDomains: SettingsDomain[] = [
  {
    id: 'site',
    title: '站点设置',
    icon: 'fas fa-sliders-h',
    permission: 'user:read',
    defaultSection: 'info',
    sections: [
      { path: 'site/info', label: '站点信息' },
      { path: 'site/notice', label: '站点公告' },
      { path: 'site/navigation', label: '导航模块' },
    ],
  },
  {
    id: 'iam',
    title: '用户与权限',
    icon: 'fas fa-users',
    permission: 'user:read',
    defaultSection: 'users',
    sections: [
      { path: 'iam/users', label: '用户管理' },
      { path: 'iam/roles', label: '角色权限管理' },
    ],
  },
  {
    id: 'auth',
    title: '认证设置',
    icon: 'fas fa-shield-alt',
    permission: ['auth:manage_provider', 'user:read'],
    defaultSection: 'methods',
    sections: [
      { path: 'auth/methods', label: '认证方式' },
      { path: 'auth/oauth-providers', label: 'OAuth 提供方', permission: 'auth:manage_provider' },
    ],
  },
  {
    id: 'appearance',
    title: '外观与主题',
    icon: 'fas fa-palette',
    defaultSection: 'presets',
    sections: [
      { path: 'appearance/presets', label: '主题预设' },
      { path: 'appearance/fine-tuning', label: '外观微调' },
    ],
  },
  {
    id: 'security',
    title: '安全设置',
    icon: 'fas fa-shield-halved',
    permission: 'user:read',
    defaultSection: 'access-control',
    sections: [
      { path: 'security/access-control', label: '访问控制' },
    ],
  },
  {
    id: 'operations',
    title: '运维设置',
    icon: 'fas fa-wrench',
    permission: 'log:manage',
    defaultSection: 'log-maintenance',
    sections: [
      { path: 'operations/log-maintenance', label: '日志维护' },
    ],
  },
]

/** 判定用户对某域的可见性 */
export function canAccessDomain(domain: SettingsDomain, hasAny: (...p: string[]) => boolean): boolean {
  if (!domain.permission) return true
  if (Array.isArray(domain.permission)) return hasAny(...domain.permission)
  return hasAny(domain.permission)
}

/** 判定用户对某分区的可见性（继承域门槛；显式分区门槛叠加） */
export function canAccessSection(
  domain: SettingsDomain,
  section: SettingsSection,
  hasAny: (...p: string[]) => boolean,
): boolean {
  if (!canAccessDomain(domain, hasAny)) return false
  if (section.permission) return hasAny(section.permission)
  return true
}

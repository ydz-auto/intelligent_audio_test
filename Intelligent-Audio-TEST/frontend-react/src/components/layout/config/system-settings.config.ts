import type { NavGroup, SidebarView } from '../types'

import { SETTINGS_DOMAINS } from '@/features/system-settings/domains'

/**
 * 系统设置 drill-in 视图（INT-347 §3.2 定稿：六域树，INT-417 收敛后）：
 * 侧栏树整树替换 + 「返回工作台」（/dashboard，INT-346 定稿）。
 * 树内权限过滤经 application hooks（use-sidebar-view 对 nested view 同样过滤
 * requiredPermission/requiredPermissions，对齐 newAPI「隐藏而非置灰」）。
 * 分区 URL 为 path 风格：/system-settings/<域>/<分区>。
 */
export const SYSTEM_SETTINGS_VIEW: SidebarView = {
  id: 'system-settings',
  pathPattern: /^\/system-settings(\/|$)/,
  parent: { to: '/dashboard', label: '返回工作台' },
  getNavGroups: (): NavGroup[] => [
    {
      id: 'settings-management',
      title: '系统管理',
      items: SETTINGS_DOMAINS.map((domain) => ({
        title: domain.title,
        icon: domain.icon,
        requiredPermission: domain.requiredPermission,
        requiredPermissions: domain.requiredPermissions,
        items: domain.sections.map((section) => ({
          title: section.title,
          url: `/system-settings/${domain.id}/${section.id}`,
          requiredPermission: section.requiredPermission,
          requiredPermissions: section.requiredPermissions,
        })),
      })),
    },
  ],
}

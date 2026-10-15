import {
  KeyRound,
  ListTree,
  Settings,
  Star,
  Tags,
  UserCog,
  Users,
} from 'lucide-react'

import type { NavGroup, SidebarView } from '../types'

/**
 * 系统设置 drill-in 视图（04_控制台.md §3.2：侧栏树整树替换 + 「返回控制台」）。
 * 分区树为可视稿占位，正式树以 INT-347 设置工作区卡定稿为准。
 */
export const SYSTEM_SETTINGS_VIEW: SidebarView = {
  id: 'system-settings',
  pathPattern: /^\/system-settings/,
  parent: { to: '/dashboard', label: '返回控制台' },
  getNavGroups: (): NavGroup[] => [
    {
      id: 'settings-basics',
      title: '基础',
      items: [
        { title: '站点设置', url: '/system-settings/site', icon: Settings },
        { title: '用户管理', url: '/system-settings/users', icon: Users },
        { title: '角色与权限', url: '/system-settings/roles', icon: UserCog },
      ],
    },
    {
      id: 'settings-testing',
      title: '测试域',
      items: [
        {
          title: '算法配置',
          url: '/system-settings/algorithms',
          icon: ListTree,
        },
        {
          title: '评估维度',
          url: '/system-settings/evaluation',
          icon: Star,
          requiredPermission: 'evaluation:read',
        },
        { title: 'SPL 映射', url: '/system-settings/spl', icon: KeyRound },
        { title: '标签管理', url: '/system-settings/tags', icon: Tags },
      ],
    },
  ],
}

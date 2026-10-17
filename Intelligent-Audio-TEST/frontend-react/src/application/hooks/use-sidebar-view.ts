import { useLocation } from '@tanstack/react-router'
import { useMemo } from 'react'

import { ROOT_SIDEBAR_NAV } from '@/components/layout/config/sidebar-nav.config'
import { resolveSidebarView } from '@/components/layout/lib/sidebar-view-registry'
import type {
  NavGroup,
  NavItem,
  ResolvedSidebarView,
} from '@/components/layout/types'
import { usePermissions } from '@/application/hooks/use-permissions'

/** 根导航在动画 key 上的哨兵值 */
const ROOT_VIEW_KEY = '__root'

/**
 * 导航项权限过滤（application 层，INT-347 §7：SidebarView 与根导航共用）：
 * - NavLink / NavCollapsible 自身按 requiredPermission / requiredPermissions 判定；
 * - NavCollapsible 子项逐项独立过滤（如自定义角色持 role:read 无 auth:manage_provider：
 *   认证设置域可见，域内仅展开「认证方式」子项——对齐 newAPI use-sidebar-view 组内逐项过滤）；
 * - 不满足者整项隐藏（不是置灰），子项全过滤掉时父折叠项整组隐藏。
 */
function filterNavItems(items: NavItem[], hasPermission: (p: string) => boolean, hasAnyPermission: (ps: string[]) => boolean): NavItem[] {
  const result: NavItem[] = []
  for (const item of items) {
    if (item.requiredPermission && !hasPermission(item.requiredPermission)) continue
    if (item.requiredPermissions && !hasAnyPermission(item.requiredPermissions)) continue

    if (item.items) {
      const subItems = item.items.filter((sub) => {
        if (sub.requiredPermission && !hasPermission(sub.requiredPermission)) return false
        if (sub.requiredPermissions && !hasAnyPermission(sub.requiredPermissions)) return false
        return true
      })
      if (subItems.length === 0) continue
      result.push({ ...item, items: subItems })
      continue
    }
    result.push(item)
  }
  return result
}

/**
 * 解析当前侧栏视图（drill-in 机制，application 层）。
 * - URL 命中注册的嵌套视图（如系统设置）→ 返回该视图导航组（同样按权限码过滤）；
 * - 否则返回根导航，按权限码过滤，空组整组隐藏（04_控制台.md §5 guest 行为）。
 * 权限码取自真实会话数据（useAuthStore.user.permissions；壳 INT-607 接线确认）。
 */
export function useSidebarView(): ResolvedSidebarView {
  const pathname = useLocation({ select: (l) => l.pathname })
  const { hasPermission, hasAnyPermission } = usePermissions()

  const rootNavGroups = useMemo<NavGroup[]>(() => {
    return ROOT_SIDEBAR_NAV.map((group) => ({
      ...group,
      items: filterNavItems(group.items, hasPermission, hasAnyPermission),
    })).filter((group) => group.items.length > 0)
  }, [hasPermission, hasAnyPermission])

  const view = resolveSidebarView(pathname)

  if (view) {
    const navGroups = view
      .getNavGroups()
      .map((group) => ({
        ...group,
        items: filterNavItems(group.items, hasPermission, hasAnyPermission),
      }))
      .filter((group) => group.items.length > 0)
    return {
      key: view.id,
      view,
      navGroups,
    }
  }

  return {
    key: ROOT_VIEW_KEY,
    view: null,
    navGroups: rootNavGroups,
  }
}

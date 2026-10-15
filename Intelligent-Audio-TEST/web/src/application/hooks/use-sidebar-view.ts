import { useLocation } from '@tanstack/react-router'
import { useMemo } from 'react'

import { ROOT_SIDEBAR_NAV } from '@/components/layout/config/sidebar-nav.config'
import { resolveSidebarView } from '@/components/layout/lib/sidebar-view-registry'
import type {
  NavGroup,
  ResolvedSidebarView,
} from '@/components/layout/types'
import { usePermissions } from '@/application/hooks/use-permissions'

/** 根导航在动画 key 上的哨兵值 */
const ROOT_VIEW_KEY = '__root'

/**
 * 解析当前侧栏视图（drill-in 机制，application 层）。
 * - URL 命中注册的嵌套视图（如系统设置）→ 返回该视图导航组；
 * - 否则返回根导航，按权限码过滤，空组整组隐藏（04_控制台.md §5 guest 行为）。
 * TODO(API 接线): 权限码换真实会话数据（mock 会话 permissions=['*'] 全通过）。
 */
export function useSidebarView(): ResolvedSidebarView {
  const pathname = useLocation({ select: (l) => l.pathname })
  const { hasPermission, hasAnyPermission } = usePermissions()

  const rootNavGroups = useMemo<NavGroup[]>(() => {
    return ROOT_SIDEBAR_NAV.map((group) => ({
      ...group,
      items: group.items.filter((item) => {
        if (item.requiredPermission) return hasPermission(item.requiredPermission)
        if (item.requiredPermissions) return hasAnyPermission(item.requiredPermissions)
        return true
      }),
    })).filter((group) => group.items.length > 0)
  }, [hasPermission, hasAnyPermission])

  const view = resolveSidebarView(pathname)

  if (view) {
    return {
      key: view.id,
      view,
      navGroups: view.getNavGroups(),
    }
  }

  return {
    key: ROOT_VIEW_KEY,
    view: null,
    navGroups: rootNavGroups,
  }
}

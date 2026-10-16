import { useMemo } from 'react'
import { hasPermission } from '@/domain/models/user'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import type { TopNavLink } from '@/components/layout/types'

/**
 * 顶部导航链接（application 层）。
 * 文案定稿：主页→工作台→报告→排行榜→文档→关于（02_导航栏.md §2.2；INT-486 全站无「控制台」）。
 * 权限过滤：导航项按页面门槛隐藏——「报告」report:read 无码隐藏（15_报告域.md §6）；
 * 其余项按各自页面卡口径（TODO(API 接线): 可见性按后端导航模块配置 + 权限码过滤）。
 */
export function useTopNavLinks(): TopNavLink[] {
  const user = useAuthStore((s) => s.user)
  return useMemo(() => {
    const links: TopNavLink[] = [
      { title: '主页', href: '/' },
      { title: '工作台', href: '/dashboard' },
      { title: '报告', href: '/reports' },
      { title: '排行榜', href: '/rankings' },
      { title: '文档', href: '/user-guide' },
      { title: '关于', href: '/about' },
    ]
    return links.filter((link) => {
      if (link.href === '/reports' || link.href === '/rankings') {
        return hasPermission(user, 'report:read')
      }
      return true
    })
  }, [user])
}

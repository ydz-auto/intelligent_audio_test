import { useMemo } from 'react'
import { hasPermission } from '@/domain/models/user'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import type { TopNavLink } from '@/components/layout/types'

/**
 * 顶部导航链接（application 层）。
 * 文案定稿：主页→工作台→报告→排行榜→文档→关于（02_导航栏.md §2.2；INT-486 全站无「控制台」）。
 * RBAC 过滤（隐藏而非置灰，基座卡 §9.2；00 总表 §4.1 顶部导航项结果行）：
 * - 主页/文档/关于：全员（含未登录）；
 * - 工作台：登录即可，未登录为受限项（requiresAuth，公共站头弹「需要登录」Dialog）；
 * - 报告：`report:read`（admin/tester/algo_engineer/guest；device_admin 隐藏）；
 * - 排行榜：`benchmark:ranking:read`（admin 通配/tester/algo_engineer，INT-429 已授；
 *   device_admin/guest/未登录隐藏）。
 * 站点级模块开关（enabled/requireAuth）待后端立项，前端常量驱动（本文件唯一源；
 * 原 components/layout/config/top-nav.config.ts 同值副本已删除，避免双份漂移）。
 */
const TOP_NAV_DEFS: TopNavLink[] = [
  { title: '主页', href: '/' },
  { title: '工作台', href: '/dashboard', requiresAuth: true },
  { title: '报告', href: '/reports', permission: 'report:read' },
  {
    title: '排行榜',
    href: '/rankings',
    permission: 'benchmark:ranking:read',
  },
  { title: '文档', href: '/user-guide' },
  { title: '关于', href: '/about' },
]

export function useTopNavLinks(): TopNavLink[] {
  const user = useAuthStore((s) => s.user)
  return useMemo(() => {
    return TOP_NAV_DEFS.filter((link) => {
      if (link.requiresAuth && !user) return true // 受限项：未登录保留，点击弹登录 Dialog
      if (link.permission && !hasPermission(user, link.permission)) return false
      return true
    })
  }, [user])
}
